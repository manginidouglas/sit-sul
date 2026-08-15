"""Coletor Onda 1 para a distribuição oficial RAIS 2024 VINC_PUB."""

from __future__ import annotations

import json
import hashlib
import ftplib
import re
from datetime import UTC, datetime
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, urlopen
from urllib.parse import urljoin

from ice_sul.extract.contracts import CollectionResult, CollectionStatus
from ice_sul.extract.http import TracingRedirect, download
from ice_sul.extract.registry import register_collector
from ice_sul.transform.rais import load_municipality_map, transform_archive

OFFICIAL_ROOT = "https://ftp.mtps.gov.br/pdet/microdados/RAIS/2024"
DE_PARA_URL = f"{OFFICIAL_ROOT}/De-Para%20Microdados.xlsx"
RAIS_2024_PORTAL_URL = "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/rais/rais-2024"
IBGE_MUNICIPALITIES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=id"
UF_CODES = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()


@dataclass(frozen=True)
class RaisArchive:
    uf: str
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def official_archives() -> list[RaisArchive]:
    return [RaisArchive(uf, f"{OFFICIAL_ROOT}/RAIS_VINC_PUB_{uf}.7z") for uf in UF_CODES]


class OfficialRoutesUnavailable(OSError):
    def __init__(self, attempts: list[dict[str, object]]):
        super().__init__("rotas oficiais HTTPS e FTP indisponíveis")
        self.attempts = attempts


def _base_manifest(*, url: str, method: str, destination: Path, uf: str) -> dict[str, object]:
    return {
        "fonte": "MTE/PDET RAIS VINC_PUB", "url": url, "metodo": method,
        "parametros": {}, "periodo": "2024", "data_hora_utc": datetime.now(UTC).isoformat(),
        "status_http": None, "resposta_ftp": None, "url_final": None, "redirects": [],
        "content_type": None, "uf": uf, "tamanho_transferido": None,
        "tamanho_persistido": None, "sha256": None, "arquivo": str(destination),
        "licenca": "não informada na distribuição consultada", "versao_snapshot": "RAIS 2024 VINC_PUB",
        "validacao": "download ainda não validado",
    }


def _download_https(url: str, destination: Path, *, uf: str) -> dict[str, object]:
    """Transfere por HTTPS em blocos, sem manter o `.7z` inteiro em memória."""
    if destination.exists():
        raise FileExistsError(f"raw imutável já existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256(); size = 0
    redirect = TracingRedirect(); opener = build_opener(redirect)
    try:
        with opener.open(Request(url, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}), timeout=180) as response, temporary.open("xb") as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk); digest.update(chunk); size += len(chunk)
            status, final_url, content_type = response.status, response.url, response.headers.get("Content-Type")
        if not size: raise ValueError("arquivo RAIS vazio")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    manifest = _base_manifest(url=url, method="GET", destination=destination, uf=uf)
    manifest.update(status_http=status, url_final=final_url, content_type=content_type,
                    redirects=redirect.history,
                    tamanho_transferido=size, tamanho_persistido=destination.stat().st_size,
                    sha256=digest.hexdigest(), validacao="recebido_não_vazio; SHA-256 calculado")
    return manifest


def _download_ftp(host: str, remote_path: str, destination: Path, *, uf: str) -> dict[str, object]:
    """Fallback oficial FTP anônimo com escrita incremental e arquivo parcial."""
    if destination.exists(): raise FileExistsError(f"raw imutável já existe: {destination}")
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256(); size = 0
    ftp_url = f"ftp://{host}{remote_path}"
    try:
        with ftplib.FTP() as ftp:
            response_connect = ftp.connect(host, 21, timeout=180)
            response_login = ftp.login()
            with temporary.open("xb") as output:
                def receive(chunk: bytes) -> None:
                    nonlocal size
                    output.write(chunk); digest.update(chunk); size += len(chunk)
                response_transfer = ftp.retrbinary(f"RETR {remote_path}", receive, blocksize=8 * 1024 * 1024)
        if not size: raise ValueError("arquivo RAIS FTP vazio")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True); raise
    manifest = _base_manifest(url=ftp_url, method="FTP RETR", destination=destination, uf=uf)
    manifest.update(resposta_ftp={"connect": response_connect, "login": response_login, "transfer": response_transfer},
                    url_final=ftp_url, redirects="nao_aplicavel", content_type="nao_aplicavel",
                    tamanho_transferido=size, tamanho_persistido=destination.stat().st_size,
                    sha256=digest.hexdigest(), validacao="recebido_não_vazio; SHA-256 calculado")
    return manifest


def download_large(url: str, destination: Path, *, uf: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Tenta as duas rotas oficiais, HTTPS e então FTP, registrando ambas."""
    attempts: list[dict[str, object]] = []
    try:
        return _download_https(url, destination, uf=uf), attempts
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        attempt = _base_manifest(url=url, method="GET", destination=destination, uf=uf)
        attempt.update(validacao="falha de acesso HTTPS", erro=f"{type(exc).__name__}: {exc}")
        if isinstance(exc, HTTPError): attempt["status_http"] = exc.code
        attempts.append(attempt)
    remote_path = "/pdet/microdados/RAIS/2024/" + destination.name
    try:
        return _download_ftp("ftp.mtps.gov.br", remote_path, destination, uf=uf), attempts
    except ftplib.all_errors as exc:
        ftp_url = f"ftp://ftp.mtps.gov.br{remote_path}"
        attempt = _base_manifest(url=ftp_url, method="FTP RETR", destination=destination, uf=uf)
        attempt.update(validacao="falha de acesso FTP", erro=f"{type(exc).__name__}: {exc}")
        attempts.append(attempt)
        raise OfficialRoutesUnavailable(attempts) from exc


def download_de_para(destination: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Obtém a planilha oficial, com fallback para o portal gov.br da RAIS 2024."""
    attempts: list[dict[str, object]] = []
    try:
        return download(DE_PARA_URL, destination, source="MTE/PDET RAIS 2024", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180), attempts
    except (HTTPError, URLError, TimeoutError) as exc:
        attempts.append({"fonte": "MTE/PDET RAIS 2024", "url": DE_PARA_URL, "metodo": "GET", "validacao": "falha da rota HTTPS do PDET", "erro": f"{type(exc).__name__}: {exc}"})
    try:
        with urlopen(Request(RAIS_2024_PORTAL_URL, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}), timeout=60) as response:
            page = response.read().decode("utf-8", "replace")
        links = re.findall(r'href=["\']([^"\']+\.xlsx(?:\?[^"\']*)?)["\']', page, flags=re.I)
        candidates = [urljoin(RAIS_2024_PORTAL_URL, link) for link in links if "de-para" in link.lower() or "de_para" in link.lower()]
        if not candidates: raise ValueError("página oficial RAIS 2024 não expôs link De-Para .xlsx")
        return download(candidates[0], destination, source="MTE — portal gov.br RAIS 2024", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180), attempts
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        attempts.append({"fonte": "MTE — portal gov.br RAIS 2024", "url": RAIS_2024_PORTAL_URL, "metodo": "GET + descoberta de link", "validacao": "falha do fallback oficial da planilha", "erro": f"{type(exc).__name__}: {exc}"})
        raise OfficialRoutesUnavailable(attempts) from exc


@dataclass
class RaisCollector:
    """Implementa o contrato compartilhado sem esconder falhas de fonte/layout."""

    destination: Path = Path("data/raw/rais/2024")
    interim: Path = Path("data/interim/rais/2024")
    quality: Path = Path("reports/quality/mvp-demo-2026/rais")
    south_reference: Path = Path("data/processed/2026/municipios.csv")
    archives: list[RaisArchive] = field(default_factory=official_archives)
    source: str = "rais"

    def collect(self) -> CollectionResult:
        self.destination.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, object]] = []
        artifacts: list[str] = []
        warnings: list[str] = []
        # A planilha é evidência de layout e fica junto ao raw; não é inferida.
        de_para = self.destination / "De-Para Microdados.xlsx"
        try:
            ibge_json = self.destination / "municipios-ibge.json"
            if not ibge_json.exists():
                entries.append(download(IBGE_MUNICIPALITIES_URL, ibge_json, source="IBGE Localidades", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180))
            ibge_rows = json.loads(ibge_json.read_text(encoding="utf-8"))
            municipality_map = {}
            for item in ibge_rows:
                code = str(item["id"])
                if len(code) != 7 or code[:6] in municipality_map:
                    raise ValueError(f"cadastro IBGE nacional inválido/ambíguo: {code}")
                municipality_map[code[:6]] = code; municipality_map[code] = code
            south_map = load_municipality_map(self.south_reference)
            south_ids = sorted({value for key, value in south_map.items() if len(key) == 6})
            if not de_para.exists():
                de_para_entry, failed_attempts = download_de_para(de_para)
                entries.extend(failed_attempts); entries.append(de_para_entry)
            artifacts.append(str(de_para))
            results = []
            for spec in self.archives:
                archive = self.destination / spec.filename
                if not archive.exists():
                    archive_entry, failed_attempts = download_large(spec.url, archive, uf=spec.uf)
                    entries.extend(failed_attempts); entries.append(archive_entry)
                artifacts.append(str(archive))
                result = transform_archive(
                    archive, file_uf=spec.uf, municipality_map=municipality_map, year=2024,
                    south_municipalities=[code for code in south_ids if {"41": "PR", "42": "SC", "43": "RS"}.get(code[:2]) == spec.uf],
                )
                results.append(result)
        except ModuleNotFoundError as exc:
            return CollectionResult(self.source, CollectionStatus.BLOCKED_ENVIRONMENT, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])
        except OfficialRoutesUnavailable as exc:
            entries.extend(exc.attempts)
            return CollectionResult(self.source, CollectionStatus.BLOCKED_SOURCE, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])
        except (HTTPError, URLError, TimeoutError) as exc:
            return CollectionResult(self.source, CollectionStatus.BLOCKED_SOURCE, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])
        except ValueError as exc:
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])

        # Cada arquivo pertence a uma UF; portanto municípios não devem se repetir.
        private = [row for result in results for row in result.private_employment]
        diagnostic = [row for result in results for row in result.diversification]
        if len(private) != len({row["municipio_id"] for row in private}):
            raise ValueError("município repetido entre arquivos VINC_PUB de UF")
        if not private:
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, ["nenhum vínculo privado elegível foi produzido"])
        if len(diagnostic) != 1191 or len({row["municipio_id"] for row in diagnostic}) != 1191:
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [f"contrato MER-DIAG-01 exige 1.191 municípios; obtidos {len(diagnostic)}"])
        unmatched = sum(len(r.quality["codigos_nao_ligados"]) for r in results)
        unmatched_rows = sum(r.quality["vinculos_municipio_nao_ligado"] for r in results)
        if unmatched:
            evidence = {
                spec.uf: result.quality["codigos_nao_ligados"]
                for spec, result in zip(self.archives, results)
                if result.quality["codigos_nao_ligados"]
            }
            entries.append({"validacao": "falha de ligação territorial", "codigos_nao_ligados": evidence, "vinculos_municipio_nao_ligado": unmatched_rows})
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [f"{unmatched} códigos municipais ({unmatched_rows} vínculos ativos) não ligados; produtos não publicados"])
        self.interim.mkdir(parents=True, exist_ok=True); self.quality.mkdir(parents=True, exist_ok=True)
        import csv
        with (self.interim / "emprego_privado_municipal.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(private[0])); writer.writeheader(); writer.writerows(sorted(private, key=lambda row: row["municipio_id"]))
        with (self.interim / "mer_diag_01.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["municipio_id", "indicador_id", "valor_bruto", "periodo_referencia", "flag_qualidade", "motivo_qualidade"]); writer.writeheader(); writer.writerows(sorted(diagnostic, key=lambda row: row["municipio_id"]))
        qa = {
            "ano": 2024, "ufs_processadas": [spec.uf for spec in self.archives],
            "vinculos_lidos": sum(r.quality.get("vinculos_lidos", 0) for r in results),
            "vinculos_ativos_lidos": sum(r.quality.get("vinculos_ativos_lidos", 0) for r in results),
            "vinculos_municipio_nao_ligado": 0,
            "vinculos_inativos_excluidos": sum(r.quality.get("vinculos_inativos_excluidos", 0) for r in results),
            "vinculos_administracao_publica_excluidos": sum(r.quality.get("vinculos_administracao_publica_excluidos", 0) for r in results),
            "vinculos_privados_elegiveis": sum(r.quality.get("vinculos_privados_elegiveis", 0) for r in results),
            "soma_municipal": sum(int(row["empregos_formais_privados"]) for row in private),
            "municipios_ligados": sum(r.quality["municipios_ligados"] for r in results),
            "codigos_nao_ligados": {spec.uf: r.quality["codigos_nao_ligados"] for spec, r in zip(self.archives, results) if r.quality["codigos_nao_ligados"]},
        }
        qa["reconciliacao_ok"] = qa["soma_municipal"] == qa["vinculos_privados_elegiveis"]
        qa_path = self.quality / "qa.json"; qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts += [str(self.interim / "emprego_privado_municipal.csv"), str(self.interim / "mer_diag_01.csv"), str(qa_path)]
        return CollectionResult(self.source, CollectionStatus.SUCCESS, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings)


register_collector("rais", RaisCollector)
