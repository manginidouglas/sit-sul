"""Coletor Onda 1 para a distribuição oficial RAIS 2024 VINC_PUB."""

from __future__ import annotations

import json
import hashlib
import ftplib
import re
import zipfile
from html.parser import HTMLParser
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, urlopen
from urllib.parse import urljoin

from ice_sul.extract.contracts import CollectionResult, CollectionStatus
from ice_sul.extract.http import TracingRedirect, download
from ice_sul.extract.registry import register_collector
from ice_sul.transform.rais import load_municipality_map, transform_archive

OFFICIAL_ROOT = "https://ftp.mtps.gov.br/pdet/microdados/RAIS/2024"
DE_PARA_URL = ("https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/"
    "acoes-e-programas/programas-projetos-acoes-obras-e-atividades/estatisticas-trabalho/"
    "rais/rais-2024/rais-2024-1/de-para-microdados.xlsx/@@download/file")
RAIS_2024_PORTAL_URL = ("https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/"
    "acoes-e-programas/programas-projetos-acoes-obras-e-atividades/estatisticas-trabalho/"
    "comunicados/comunicado-microdados-rais-2024")
IBGE_MUNICIPALITIES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=id"
UF_CODES = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()


@dataclass(frozen=True)
class RaisArchive:
    uf: str
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.links: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a" and (href := dict(attrs).get("href")):
            self.links.append(href)


def archives_from_listing(links: list[str]) -> list[RaisArchive]:
    """Seleciona VINC_PUB apenas de nomes efetivamente listados pela fonte."""
    found: dict[str, RaisArchive] = {}
    for link in links:
        name = link.rstrip("/").rsplit("/", 1)[-1]
        match = re.fullmatch(r"RAIS_VINC_PUB_([A-Z]{2})\.7z", name, re.I)
        if not match:
            continue
        uf = match.group(1).upper()
        if uf not in UF_CODES or uf in found:
            raise ValueError(f"arquivo VINC_PUB inválido/duplicado na listagem: {name}")
        found[uf] = RaisArchive(uf, urljoin(OFFICIAL_ROOT + "/", link))
    missing = sorted(set(UF_CODES) - found.keys())
    if missing:
        raise ValueError(f"listagem oficial RAIS 2024 incompleta; UFs ausentes: {missing}")
    return [found[uf] for uf in UF_CODES]


def discover_official_archives() -> tuple[list[RaisArchive], dict[str, object]]:
    """Lista o diretório oficial; nomes de arquivos nunca são sintetizados."""
    redirect = TracingRedirect(); opener = build_opener(redirect)
    with opener.open(Request(OFFICIAL_ROOT + "/", headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}), timeout=180) as response:
        body = response.read(); parser = _Links(); parser.feed(body.decode("utf-8", "replace"))
        archives = archives_from_listing(parser.links)
        entry = _base_manifest(url=OFFICIAL_ROOT + "/", method="GET (listagem)", destination=Path(""), uf="BR")
        entry.update(status_http=response.status, url_final=response.url, redirects=redirect.history,
                     content_type=response.headers.get("Content-Type"), tamanho_transferido=len(body),
                     tamanho_persistido=0, sha256=hashlib.sha256(body).hexdigest(), arquivo=None,
                     validacao=f"listagem validada; {len(archives)} arquivos VINC_PUB únicos")
        return archives, entry


def validate_xlsx(path: Path) -> str:
    try:
        if not zipfile.is_zipfile(path):
            raise ValueError(f"XLSX inválido (não é ZIP OOXML): {path}")
        with zipfile.ZipFile(path) as workbook:
            bad = workbook.testzip(); names = set(workbook.namelist())
            if bad or not {"[Content_Types].xml", "xl/workbook.xml"} <= names:
                raise ValueError(f"XLSX corrompido/incompleto: {path}; membro={bad}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"XLSX ilegível: {path}: {exc}") from exc
    return "XLSX OOXML íntegro"


def validate_7z(path: Path) -> str:
    try:
        import py7zr
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("py7zr é necessário para validar RAIS .7z") from exc
    if not py7zr.is_7zfile(path):
        raise ValueError(f"assinatura 7-Zip inválida: {path}")
    with py7zr.SevenZipFile(path) as archive:
        names = archive.getnames()
        if archive.test() is not None or len([n for n in names if n.lower().endswith(".comt")]) != 1:
            raise ValueError(f"7-Zip corrompido ou layout inesperado: {path}")
    return "7-Zip íntegro; exatamente um membro .comt"


def reused_manifest(path: Path, *, url: str, uf: str, validation: str) -> dict[str, object]:
    entry = _base_manifest(url=url, method="REUSE", destination=path, uf=uf)
    size = path.stat().st_size
    entry.update(url_final=url, redirects=[], content_type="application/x-7z-compressed" if path.suffix == ".7z" else
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 tamanho_transferido=0, tamanho_persistido=size,
                 sha256=hashlib.sha256(path.read_bytes()).hexdigest(), validacao=validation,
                 reutilizado=True)
    return entry


def complete_small_manifest(entry: dict[str, object], *, path: Path, license_text: str,
                            snapshot: str) -> dict[str, object]:
    """Completa o manifesto do adaptador HTTP compartilhado sem perder campos."""
    size = int(entry["tamanho"])
    entry.update(tamanho_transferido=size, tamanho_persistido=path.stat().st_size,
                 licenca=license_text, versao_snapshot=snapshot)
    return entry


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
    """Obtém o recurso oficial e redescobre o link no comunicado se necessário."""
    attempts: list[dict[str, object]] = []
    try:
        entry = download(DE_PARA_URL, destination, source="MTE/PDET RAIS 2024", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180)
        complete_small_manifest(entry, path=destination,
                                license_text="não informada no recurso consultado",
                                snapshot="RAIS 2024 De-Para")
        entry["validacao"] = validate_xlsx(destination)
        return entry, attempts
    except (HTTPError, URLError, TimeoutError) as exc:
        attempts.append({"fonte": "MTE/PDET RAIS 2024", "url": DE_PARA_URL, "metodo": "GET", "validacao": "falha da rota HTTPS do PDET", "erro": f"{type(exc).__name__}: {exc}"})
    try:
        with urlopen(Request(RAIS_2024_PORTAL_URL, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}), timeout=60) as response:
            page = response.read().decode("utf-8", "replace")
        parser = _Links(); parser.feed(page)
        candidates = [urljoin(RAIS_2024_PORTAL_URL, link) for link in parser.links
                      if ("de-para" in link.lower() or "de_para" in link.lower())
                      and (".xlsx" in link.lower() or "@@download/file" in link.lower())]
        if not candidates: raise ValueError("comunicado oficial RAIS 2024 não expôs link De-Para")
        entry = download(candidates[0], destination, source="MTE — comunicado de microdados RAIS 2024", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180)
        complete_small_manifest(entry, path=destination,
                                license_text="não informada no recurso consultado",
                                snapshot="RAIS 2024 De-Para")
        entry["validacao"] = validate_xlsx(destination)
        return entry, attempts
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
    archives: list[RaisArchive] | None = None
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
                ibge_entry = download(IBGE_MUNICIPALITIES_URL, ibge_json, source="IBGE Localidades", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180)
                entries.append(complete_small_manifest(ibge_entry, path=ibge_json,
                    license_text="dados públicos IBGE", snapshot="Localidades na data da coleta"))
            else:
                entries.append(reused_manifest(ibge_json, url=IBGE_MUNICIPALITIES_URL, uf="BR", validation="JSON será validado integralmente"))
            ibge_rows = json.loads(ibge_json.read_text(encoding="utf-8"))
            municipality_map = {}
            for item in ibge_rows:
                code = str(item["id"])
                if len(code) != 7 or code[:6] in municipality_map:
                    raise ValueError(f"cadastro IBGE nacional inválido/ambíguo: {code}")
                municipality_map[code[:6]] = code; municipality_map[code] = code
            south_map = load_municipality_map(self.south_reference)
            south_ids = sorted({value for key, value in south_map.items() if len(key) == 6})
            if not isinstance(ibge_rows, list) or not ibge_rows:
                raise ValueError("cadastro IBGE nacional não é lista não vazia")
            if not de_para.exists():
                de_para_entry, failed_attempts = download_de_para(de_para)
                entries.extend(failed_attempts); entries.append(de_para_entry)
            else:
                entries.append(reused_manifest(de_para, url=DE_PARA_URL, uf="BR", validation=validate_xlsx(de_para)))
            artifacts.append(str(de_para))
            archives = self.archives
            if archives is None:
                archives, listing_entry = discover_official_archives()
                entries.append(listing_entry)
            results = []
            for spec in archives:
                archive = self.destination / spec.filename
                if not archive.exists():
                    archive_entry, failed_attempts = download_large(spec.url, archive, uf=spec.uf)
                    archive_entry["validacao"] = validate_7z(archive)
                    entries.extend(failed_attempts); entries.append(archive_entry)
                else:
                    entries.append(reused_manifest(archive, url=spec.url, uf=spec.uf, validation=validate_7z(archive)))
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
                for spec, result in zip(archives, results)
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
            "ano": 2024, "ufs_processadas": [spec.uf for spec in archives],
            "vinculos_lidos": sum(r.quality.get("vinculos_lidos", 0) for r in results),
            "vinculos_ativos_lidos": sum(r.quality.get("vinculos_ativos_lidos", 0) for r in results),
            "vinculos_municipio_nao_ligado": 0,
            "vinculos_inativos_excluidos": sum(r.quality.get("vinculos_inativos_excluidos", 0) for r in results),
            "vinculos_administracao_publica_excluidos": sum(r.quality.get("vinculos_administracao_publica_excluidos", 0) for r in results),
            "vinculos_privados_elegiveis": sum(r.quality.get("vinculos_privados_elegiveis", 0) for r in results),
            "soma_municipal": sum(int(row["empregos_formais_privados"]) for row in private),
            "municipios_ligados": sum(r.quality["municipios_ligados"] for r in results),
            "codigos_nao_ligados": {spec.uf: r.quality["codigos_nao_ligados"] for spec, r in zip(archives, results) if r.quality["codigos_nao_ligados"]},
            "semantica_base_nacional": "esparsa: uma linha por município com estoque privado positivo; ausência equivale a zero somente após sucesso das 27 UFs e ligação territorial integral",
        }
        qa["reconciliacao_ok"] = qa["soma_municipal"] == qa["vinculos_privados_elegiveis"]
        qa_path = self.quality / "qa.json"; qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts += [str(self.interim / "emprego_privado_municipal.csv"), str(self.interim / "mer_diag_01.csv"), str(qa_path)]
        return CollectionResult(self.source, CollectionStatus.SUCCESS, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings)


register_collector("rais", RaisCollector)
