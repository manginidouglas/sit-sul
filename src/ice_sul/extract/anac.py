"""Coleta idempotente, retomável e auditável dos arquivos oficiais da ANAC."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import CollectionResult, CollectionStatus
from .registry import register_collector

MOVEMENTS_URL = "https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/Dados_Estatisticos.csv"
PUBLIC_URL = "https://sistemas.anac.gov.br/dadosabertos/Aerodromos/Aer%C3%B3dromos%20P%C3%BAblicos/Lista%20de%20aer%C3%B3dromos%20p%C3%BAblicos/AerodromosPublicos.csv"
PRIVATE_BASE = "https://sistemas.anac.gov.br/dadosabertos/Aerodromos/Aer%C3%B3dromos%20Privados/Lista%20de%20aer%C3%B3dromos%20privados"
PRIVATE_URL = PRIVATE_BASE + "/Aerodromos%20Privados/AerodromosPrivados.csv"
HELIPORTS_URL = PRIVATE_BASE + "/Heliponto/Helipontos.csv"
HELIDECKS_URL = PRIVATE_BASE + "/Helideck/Helidecks.csv"
SIROS_URL = "https://siros.anac.gov.br/siros/registros/aerodromo/aerodromos.csv"
AERODROMES_URL = PUBLIC_URL  # compatibilidade com integrações anteriores
PUBLIC_PAGE = "https://www.anac.gov.br/acesso-a-informacao/dados-abertos/areas-de-atuacao/aerodromos/lista-de-aerodromos-publicos-v2"
PRIVATE_PAGE = "https://www.anac.gov.br/acesso-a-informacao/dados-abertos/areas-de-atuacao/aerodromos/lista-de-aerodromos-privados-v2"
UA = "SIT-mvp-demo-2026/2.0 (+dados-publicos)"


class ValidationError(ValueError):
    """Bytes recebidos, mas estruturalmente inválidos."""


def sha256_stream(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_content_type(value: str | None) -> None:
    value = (value or "").lower()
    if value and not any(kind in value for kind in ("csv", "text/plain", "octet-stream", "excel")):
        raise ValidationError(f"Content-Type incompatível com CSV: {value}")


def _entry(path: Path, url: str, *, action: str, metadata: dict[str, object], attempts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "fonte": "ANAC", "url_download": url, "metodo": "GET", "parametros": {},
        "data_coleta_utc": metadata.get("timestamp", _now()), "status_http": metadata.get("status_http"),
        "url_final": metadata.get("url_final", url), "redirects": metadata.get("redirects", []),
        "content_type": metadata.get("content_type"), "content_length": metadata.get("content_length"),
        "tamanho_transferido": metadata.get("tamanho_transferido", 0 if action == "reused" else path.stat().st_size),
        "tamanho_persistido": path.stat().st_size, "sha256": sha256_stream(path), "arquivo": str(path),
        "licenca": "Dados Abertos ANAC (dados.gov.br)", "etag": metadata.get("etag"),
        "last_modified": metadata.get("last_modified"), "status": action, "tentativas": attempts,
    }


def download_resumable(
    url: str, destination: Path, *, validator: Callable[[Path], str] | None = None,
    timeout: float = 120, attempts: int = 6, minimum_size: int = 1024,
    expected_sha256: str | None = None, frozen_entry: dict[str, object] | None = None,
    opener=urlopen, sleeper=time.sleep, revalidation_utc: str | None = None,
) -> dict[str, object]:
    """Valida/reutiliza raw ou baixa em ``.part`` e promove só após validação."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    validator = validator or (lambda _path: "validado")
    logs: list[dict[str, object]] = []
    if destination.exists():
        try:
            if destination.stat().st_size < minimum_size:
                raise ValidationError("recurso menor que o tamanho mínimo plausível")
            version = validator(destination)
            digest = sha256_stream(destination)
            if expected_sha256 and digest != expected_sha256:
                raise ValidationError("SHA-256 do raw diverge do manifesto")
        except (ValueError, UnicodeError, csv.Error) as exc:
            raise ValidationError(f"raw existente inválido: {exc}") from exc
        metadata = dict(frozen_entry or {})
        metadata["timestamp"] = metadata.get("data_coleta_utc", _now())
        item = _entry(destination, url, action="reused", metadata=metadata, attempts=[])
        item["data_revalidacao_utc"] = revalidation_utc or _now()
        item.update(versao_fonte=version, validacoes=["tamanho", "schema", "versao", "sha256"])
        return item

    partial = destination.with_suffix(destination.suffix + ".part")
    sidecar = partial.with_suffix(partial.suffix + ".json")
    last_error: Exception | None = None
    metadata: dict[str, object] = {}
    for attempt in range(1, attempts + 1):
        # A identidade é reavaliada em toda tentativa, inclusive após uma queda
        # ocorrida nesta mesma chamada antes da gravação do sidecar.
        saved: dict[str, object] = {}
        if partial.exists():
            try:
                saved = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
            except json.JSONDecodeError:
                saved = {}
            if not (saved.get("etag") or saved.get("last_modified")):
                partial.unlink(missing_ok=True)
                sidecar.unlink(missing_ok=True)
                saved = {}
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": UA, "Accept": "text/csv,application/octet-stream;q=.9,*/*;q=.1"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            if saved.get("etag"): headers["If-Range"] = saved["etag"]
            elif saved.get("last_modified"): headers["If-Range"] = saved["last_modified"]
        log = {"rota": url, "tentativa": attempt, "timestamp": _now(), "offset": offset}
        etag = modified = None
        try:
            response = opener(Request(url, headers=headers), timeout=timeout)
            with response:
                status = getattr(response, "status", response.getcode())
                final_url = response.geturl()
                response_headers = response.headers
                etag, modified = response_headers.get("ETag"), response_headers.get("Last-Modified")
                content_range = response_headers.get("Content-Range")
                if offset and status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range or "")
                    if not match or int(match.group(1)) != offset:
                        raise ValidationError("Content-Range incompatível com o offset solicitado")
                    if (saved.get("etag") and saved["etag"] != etag) or (saved.get("last_modified") and saved["last_modified"] != modified):
                        raise ValidationError("versão do recurso mudou durante a retomada")
                    mode = "ab"
                elif status == 206:
                    raise ValidationError("resposta 206 inesperada sem retomada identificada")
                else:
                    # Resposta 200 a Range é um novo recurso completo, nunca concatenação.
                    mode, offset = "wb", 0
                _validate_content_type(response_headers.get("Content-Type"))
                # O sidecar deve preceder os bytes. Sem identidade forte, uma
                # queda tornará o parcial descartável na próxima tentativa.
                if etag or modified:
                    sidecar.write_text(json.dumps({"etag": etag, "last_modified": modified}), encoding="utf-8")
                else:
                    sidecar.unlink(missing_ok=True)
                transferred = 0
                with partial.open(mode) as stream:
                    for block in iter(lambda: response.read(1024 * 1024), b""):
                        stream.write(block); transferred += len(block)
                metadata = {
                    "timestamp": log["timestamp"], "status_http": status, "url_final": final_url,
                    "redirects": [] if final_url == url else [final_url], "content_type": response_headers.get("Content-Type"),
                    "content_length": response_headers.get("Content-Length"), "tamanho_transferido": transferred,
                    "etag": etag, "last_modified": modified,
                }
            if partial.stat().st_size < minimum_size:
                raise ValidationError("recurso menor que o tamanho mínimo plausível")
            with partial.open("rb") as probe:
                if b"<html" in probe.read(4096).lower(): raise ValidationError("HTML recebido como CSV")
            version = validator(partial)  # portão anterior à promoção
            digest = sha256_stream(partial)
            if expected_sha256 and digest != expected_sha256:
                raise ValidationError("snapshot baixado diverge do snapshot congelado")
            partial.replace(destination); sidecar.unlink(missing_ok=True)
            log.update(status="downloaded", status_http=status); logs.append(log)
            item = _entry(destination, url, action="downloaded", metadata=metadata, attempts=logs)
            item.update(versao_fonte=version, validacoes=["content-type", "não HTML", "tamanho", "schema", "versao", "sha256"])
            return item
        except HTTPError as exc:
            last_error = exc; log.update(status=f"http_{exc.code}", erro_original=str(exc)); logs.append(log)
            if exc.code in (401, 403): raise
            if exc.code not in (429, 502, 503, 504): raise
        except ValidationError:
            partial.unlink(missing_ok=True); sidecar.unlink(missing_ok=True); raise
        except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            last_error = exc; log.update(status="transport_error", erro_original=repr(exc)); logs.append(log)
            if not (etag or modified):
                partial.unlink(missing_ok=True)
                sidecar.unlink(missing_ok=True)
        if attempt < attempts: sleeper(min(2 ** (attempt - 1), 30))
    error = RuntimeError(f"download ANAC indisponível após {attempts} tentativas: {last_error}")
    error.attempts = logs  # type: ignore[attr-defined]
    raise error


MOVEMENT_FIELDS = {"AEROPORTO_DE_ORIGEM_SIGLA", "AEROPORTO_DE_ORIGEM_NOME", "AEROPORTO_DE_ORIGEM_UF", "AEROPORTO_DE_ORIGEM_PAIS", "AEROPORTO_DE_DESTINO_SIGLA", "AEROPORTO_DE_DESTINO_NOME", "AEROPORTO_DE_DESTINO_UF", "AEROPORTO_DE_DESTINO_PAIS", "ANO", "MES", "GRUPO_DE_VOO", "NATUREZA", "DECOLAGENS", "ASSENTOS", "PASSAGEIROS_PAGOS", "PASSAGEIROS_GRATIS"}


def validate_movements(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        version = stream.readline().strip(); header = next(csv.reader(stream, delimiter=";"), [])
    missing = MOVEMENT_FIELDS - set(header)
    if not version.startswith("Atualizado em:") or missing: raise ValidationError(f"schema/versionamento inválido; ausentes: {sorted(missing)}")
    return version


def validate_aerodromes(path: Path) -> str:
    try: stream = path.open(encoding="utf-8-sig", newline=""); stream.read(4096); stream.seek(0)
    except UnicodeDecodeError: stream.close(); stream = path.open(encoding="cp1252", newline="")
    with stream:
        version = stream.readline().strip(); header = next(csv.reader(stream, delimiter=";"), [])
    normalized = {re.sub(r"[^A-Z0-9]+", " ", __import__('unicodedata').normalize("NFKD", h).encode("ascii", "ignore").decode().upper()).strip() for h in header}
    if not ({"CODIGO OACI", "CIAD", "NOME"} <= normalized):
        raise ValidationError("schema inválido no cadastro ANAC")
    if not (version.startswith("Atualizado em:") or version.startswith("Criado em:")): raise ValidationError("versão cadastral ausente")
    return version


def validate_siros(path: Path) -> str:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream, delimiter=";"), [])
    except UnicodeDecodeError:
        with path.open(encoding="cp1252", newline="") as stream:
            header = next(csv.reader(stream, delimiter=";"), [])
    normalized = {re.sub(r"[^A-Z0-9]+", " ", __import__('unicodedata').normalize("NFKD", h).encode("ascii", "ignore").decode().upper()).strip() for h in header}
    if not {"SIGLA ICAO AERODROMO", "NOME AERODROMO", "PAIS AERODROMO", "LATITUDE", "LONGITUDE"} <= normalized: raise ValidationError("schema SIROS inválido")
    return "Last-Modified HTTP"


@dataclass
class AnacCollector:
    movements_path: Path = Path("data/raw/anac/Dados_Estatisticos.csv")
    public_path: Path = Path("data/raw/anac/cadastro-aerodromos-publicos.csv")
    private_path: Path = Path("data/raw/anac/cadastro-aerodromos-privados.csv")
    heliports_path: Path = Path("data/raw/anac/helipontos.csv")
    helidecks_path: Path = Path("data/raw/anac/helidecks.csv")
    siros_path: Path = Path("data/raw/anac/aerodromos-siros.csv")
    frozen_manifest_path: Path = Path("reports/quality/mvp-demo-2026/anac/frozen-snapshot.json")
    revalidation_utc: str | None = None
    source: str = "anac"

    def collect(self) -> CollectionResult:
        entries, artifacts = [], []
        error: Exception | None = None
        status: CollectionStatus | None = None
        try:
            try:
                payload = json.loads(self.frozen_manifest_path.read_text(encoding="utf-8"))
            except FileNotFoundError as caught:
                raise ValidationError("frozen-snapshot.json ausente") from caught
            except json.JSONDecodeError as caught:
                raise ValidationError("frozen-snapshot.json inválido") from caught
            if not isinstance(payload, dict) or not isinstance(payload.get("artefatos"), list):
                raise ValidationError("frozen-snapshot.json sem lista artefatos")
            frozen: dict[str, dict[str, object]] = {}
            for entry in payload["artefatos"]:
                if not isinstance(entry, dict) or not entry.get("id") or not entry.get("sha256"):
                    raise ValidationError("entrada congelada sem id ou sha256")
                if entry["id"] in frozen:
                    raise ValidationError(f"recurso congelado duplicado: {entry['id']}")
                frozen[str(entry["id"])] = entry
            resources = (("movimentos", MOVEMENTS_URL, self.movements_path, validate_movements, 10_000_000, None), ("publicos", PUBLIC_URL, self.public_path, validate_aerodromes, 10_000, PUBLIC_PAGE), ("privativos", PRIVATE_URL, self.private_path, validate_aerodromes, 10_000, PRIVATE_PAGE), ("helipontos", HELIPORTS_URL, self.heliports_path, validate_aerodromes, 10_000, PRIVATE_PAGE), ("helidecks", HELIDECKS_URL, self.helidecks_path, validate_aerodromes, 10_000, PRIVATE_PAGE), ("siros", SIROS_URL, self.siros_path, validate_siros, 10_000, PRIVATE_PAGE))
            missing = [resource_id for resource_id, *_rest in resources if resource_id not in frozen]
            if missing:
                raise ValidationError(f"snapshot sem recursos obrigatórios: {missing}")
            for resource_id, url, path, validator, minimum, page in resources:
                expected = frozen.get(resource_id)
                if not expected: raise ValidationError(f"snapshot sem hash congelado: {resource_id}")
                item = download_resumable(url, path, validator=validator, minimum_size=minimum, expected_sha256=expected["sha256"], frozen_entry=expected, revalidation_utc=self.revalidation_utc)
                item["id"] = resource_id
                item["pagina_oficial"] = page; item["tipo_cadastro"] = "publico" if path == self.public_path else "privativo" if path == self.private_path else None
                entries.append(item); artifacts.append(str(path))
        except ValidationError as caught:
            error, status = caught, CollectionStatus.FAILED_VALIDATION
        except HTTPError as caught:
            error = caught; status = CollectionStatus.BLOCKED_SOURCE if caught.code in (401, 403) else CollectionStatus.UNAVAILABLE
        except (PermissionError, OSError) as caught:
            error, status = caught, CollectionStatus.BLOCKED_ENVIRONMENT
        except (URLError, TimeoutError, socket.timeout, ConnectionError) as caught:
            error, status = caught, CollectionStatus.BLOCKED_ENVIRONMENT
        except RuntimeError as caught:
            error, status = caught, CollectionStatus.UNAVAILABLE
        except Exception as caught:
            error, status = caught, CollectionStatus.UNAVAILABLE
        else:
            return CollectionResult(source=self.source, status=CollectionStatus.SUCCESS, artifacts=artifacts, indicators=["INF-LOG-02", "INF-LOG-03"], manifest_entries=entries)
        assert status is not None
        assert error is not None
        return CollectionResult(source=self.source, status=status, artifacts=artifacts, indicators=["INF-LOG-02", "INF-LOG-03"], manifest_entries=entries, errors=[repr(error)])

    @staticmethod
    def write_manifest(result: CollectionResult, path: Path, *, period: str = "2025-07/2026-06") -> None:
        payload = result.as_dict(); payload["periodo"] = period
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


register_collector("anac", AnacCollector)
