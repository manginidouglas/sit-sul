"""Coletor auditável RAIS 2024: descoberta, raws validados e publicação atômica."""

from __future__ import annotations

import csv
import errno
import ftplib
import hashlib
import json
import mimetypes
import re
import socket
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

from ice_sul.extract.contracts import CollectionResult, CollectionStatus
from ice_sul.extract.http import TracingRedirect
from ice_sul.extract.registry import register_collector
from ice_sul.transform.rais import (
    UF_PREFIX,
    load_municipality_map,
    safe_member,
    transform_archive,
)

YEAR = 2024
OFFICIAL_HOST = "ftp.mtps.gov.br"
OFFICIAL_DIR = "/pdet/microdados/RAIS/2024"
OFFICIAL_ROOT = f"https://{OFFICIAL_HOST}{OFFICIAL_DIR}"
PORTAL_HOST = "www.gov.br"
IBGE_HOST = "servicodados.ibge.gov.br"
PORTAL_PAGE = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/"
    "acoes-e-programas/programas-projetos-acoes-obras-e-atividades/"
    "estatisticas-trabalho/rais/rais-2024/rais-2024-1"
)
DE_PARA_URL = PORTAL_PAGE + "/de-para-microdados.xlsx/@@download/file"
IBGE_URL = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=id"
)
UF_CODES = tuple(sorted(UF_PREFIX.values()))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
REQUIRED_FIELDS = {
    "cnae20classecódigo",
    "indvínculoativo3112código",
    "naturezajurídicacódigo",
}
MUNICIPAL_FIELDS = {"municípiotrabcódigo", "municípiocódigo"}

REGIONAL_PARTITIONS: dict[str, tuple[str, ...]] = {
    "SUL": ("PR", "SC", "RS"),
    "NORTE": ("AC", "AM", "AP", "PA", "RO", "RR", "TO"),
    "NORDESTE": ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"),
    "CENTRO_OESTE": ("DF", "GO", "MS", "MT"),
    "SP": ("SP",),
    "MG_ES_RJ": ("MG", "ES", "RJ"),
}


@dataclass(frozen=True)
class RaisArchive:
    """Uma partição publicada e a cobertura territorial que ela declara."""

    partition_id: str
    covered_ufs: tuple[str, ...]
    url: str
    year: int = YEAR

    @property
    def filename(self) -> str:
        return self.url.rstrip("/").rsplit("/", 1)[-1]


class ArchiveCoverageError(ValueError):
    def __init__(self, message: str, details: dict[str, object]):
        super().__init__(message)
        self.details = details


class OfficialRoutesUnavailable(OSError):
    def __init__(self, attempts: list[dict[str, object]]):
        super().__init__("rotas oficiais HTTPS e FTP indisponíveis")
        self.attempts = attempts


class FTPTransportError(OSError):
    pass


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a" and (href := dict(attrs).get("href")):
            self.links.append(href)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def content_type(path: Path) -> str:
    return {
        ".7z": "application/x-7z-compressed",
        ".xlsx": XLSX_MIME,
        ".json": "application/json",
    }.get(
        path.suffix.lower(),
        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )


def _manifest(
    *,
    url: str,
    method: str,
    path: Path,
    partition_id: str = "BR",
    covered_ufs: tuple[str, ...] = (),
    status: int | None = None,
    # Compatibilidade local para chamadas de recursos não particionados.
    uf: str | None = None,
) -> dict[str, object]:
    if uf is not None:
        partition_id = uf
        covered_ufs = () if uf == "BR" else (uf,)
    return {
        "fonte": "MTE/PDET RAIS",
        "url": url,
        "metodo": method,
        "parametros": {},
        "periodo": str(YEAR),
        "data_hora_utc": datetime.now(UTC).isoformat(),
        "status_http": status,
        "url_final": url,
        "redirects": [],
        "content_type": content_type(path),
        "partition_id": partition_id,
        "covered_ufs": list(covered_ufs),
        "tamanho_transferido": 0,
        "tamanho_persistido": path.stat().st_size if path.exists() else None,
        "sha256": sha256_file(path) if path.exists() else None,
        "arquivo": str(path),
        "licenca": "não informada na distribuição consultada",
        "versao_snapshot": f"RAIS {YEAR}",
        "validacao": "pendente",
        "status": "downloaded",
    }


def validate_xlsx(path: Path) -> dict[str, object]:
    if not zipfile.is_zipfile(path):
        raise ValueError(f"XLSX inválido/não OOXML: {path}")
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheets = workbook.sheetnames
            if "VINC_PUB" not in sheets:
                raise ValueError("workbook sem aba VINC_PUB")
            sheet = workbook["VINC_PUB"]
            if (
                str(sheet["A1"].value).strip().lower() != "de"
                or str(sheet["B1"].value).strip().lower() != "para"
            ):
                raise ValueError("VINC_PUB sem estrutura De/Para oficial")
            field_rows: dict[str, object] = {}
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                values = list(row)
                for value in values:
                    normalized = str(value).strip().lower() if value is not None else ""
                    if normalized in REQUIRED_FIELDS | MUNICIPAL_FIELDS:
                        field_rows[normalized] = {
                            "linha": row_number,
                            "celulas_nao_vazias": [
                                {"coluna": index + 1, "valor": item}
                                for index, item in enumerate(values)
                                if item is not None
                            ],
                        }
            target_values = set(field_rows)
            missing = REQUIRED_FIELDS - target_values
            missing_municipality = not MUNICIPAL_FIELDS & target_values
            if missing or missing_municipality:
                if missing_municipality:
                    missing = missing | {"campo_municipal"}
                raise ValueError(
                    f"VINC_PUB sem campos obrigatórios: {sorted(missing)}"
                )
            confirmed = sorted(REQUIRED_FIELDS | (MUNICIPAL_FIELDS & target_values))
        finally:
            workbook.close()
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"workbook XLSX corrompido: {exc}") from exc
    return {
        "tipo": "XLSX OOXML funcional",
        "abas": sheets,
        "campos_confirmados": confirmed,
        "linhas_campos": field_rows,
        "tamanho": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _validate_open_archive(seven) -> dict[str, object]:
    names = seven.getnames()
    if not names:
        raise ValueError("7-Zip vazio")
    for name in names:
        safe_member(name)
    candidates = [name for name in names if name.lower().endswith(".comt")]
    if len(candidates) != 1:
        raise ValueError(
            f"esperado exatamente um .comt de Vínculos; encontrados: {candidates}"
        )
    bad_member = seven.testzip()
    if bad_member is not None:
        raise ValueError(f"CRC inválido no membro: {bad_member}")
    crc_result = seven.test()
    if crc_result is False:
        raise ValueError("teste CRC do 7-Zip falhou")
    return {
        "membros": names,
        "membro_comt": candidates[0],
        "crc_result": crc_result,
        "testzip": bad_member,
    }


def validate_7z(path: Path) -> dict[str, object]:
    import py7zr

    if not py7zr.is_7zfile(path):
        raise ValueError(f"assinatura 7-Zip inválida: {path}")
    try:
        with py7zr.SevenZipFile(path) as seven:
            info = _validate_open_archive(seven)
        with tempfile.TemporaryDirectory(prefix="sit-rais-validate-") as directory:
            with py7zr.SevenZipFile(path) as seven:
                seven.extract(path=directory, targets=[info["membro_comt"]])
            member = Path(directory) / safe_member(str(info["membro_comt"]))
            with member.open("rb") as stream:
                if not stream.read(1):
                    raise ValueError("membro .comt vazio/não extraível")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"7-Zip corrompido/truncado: {exc}") from exc
    return {
        "tipo": "7-Zip",
        "membros": info["membros"],
        "membro_comt": info["membro_comt"],
        "crc_result": info["crc_result"],
        "tamanho": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def reused_manifest(
    path: Path,
    *,
    url: str,
    validation: dict[str, object],
    partition_id: str = "BR",
    covered_ufs: tuple[str, ...] = (),
    uf: str | None = None,
) -> dict[str, object]:
    entry = _manifest(
        url=url,
        method="REUSE",
        path=path,
        partition_id=partition_id,
        covered_ufs=covered_ufs,
        uf=uf,
    )
    entry.update(status="reused", reutilizado=True, validacao=validation)
    return entry


def _download_validated(
    url: str,
    destination: Path,
    *,
    validator,
    timeout: int = 180,
    partition_id: str = "BR",
    covered_ufs: tuple[str, ...] = (),
    uf: str | None = None,
) -> dict[str, object]:
    if destination.exists():
        raise FileExistsError(f"raw imutável já existe: {destination}")
    parsed = urlparse(url)
    if parsed.hostname not in {OFFICIAL_HOST, PORTAL_HOST, IBGE_HOST}:
        raise ValueError(f"host externo proibido: {parsed.hostname}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    part.unlink(missing_ok=True)
    redirect = TracingRedirect()
    opener = build_opener(redirect)
    digest = hashlib.sha256()
    size = 0
    try:
        with opener.open(
            Request(url, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}),
            timeout=timeout,
        ) as response, part.open("xb") as output:
            final = response.url
            if urlparse(final).hostname not in {
                OFFICIAL_HOST,
                PORTAL_HOST,
                IBGE_HOST,
            }:
                raise ValueError(f"redirect para host externo: {final}")
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            status = response.status
            response_content_type = response.headers.get("Content-Type")
        if not size:
            raise ValueError("download vazio")
        validation = validator(part)
        part.replace(destination)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    entry = _manifest(
        url=url,
        method="GET",
        path=destination,
        partition_id=partition_id,
        covered_ufs=covered_ufs,
        status=status,
        uf=uf,
    )
    entry.update(
        url_final=final,
        redirects=redirect.history,
        content_type=response_content_type,
        tamanho_transferido=size,
        sha256=digest.hexdigest(),
        validacao=validation,
    )
    return entry


def view_to_download(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname != PORTAL_HOST:
        raise ValueError("link De-Para fora do domínio oficial")
    if re.search(r"\.xlsx/view/?$", parsed.path, re.I):
        return url[: url.lower().rfind("/view")] + "/@@download/file"
    if "@@download/file" in parsed.path:
        return url
    raise ValueError(f"link De-Para inesperado: {url}")


def discover_de_para_url(page_html: str) -> str:
    parser = _Links()
    parser.feed(page_html)
    candidates = []
    for link in parser.links:
        absolute = urljoin(PORTAL_PAGE + "/", link)
        if "de-para" in absolute.lower() and (
            ".xlsx/view" in absolute.lower() or "@@download/file" in absolute.lower()
        ):
            candidates.append(view_to_download(absolute))
    unique = sorted(set(candidates))
    if len(unique) != 1:
        raise ValueError(
            f"esperado um link De-Para oficial; encontrados {unique}"
        )
    return unique[0]


def download_de_para(destination: Path) -> tuple[dict[str, object], list[dict]]:
    attempts: list[dict[str, object]] = []
    try:
        return (
            _download_validated(
                DE_PARA_URL,
                destination,
                partition_id="BR",
                validator=validate_xlsx,
            ),
            attempts,
        )
    except (HTTPError, URLError, TimeoutError) as exc:
        attempts.append(
            {
                "rota": "direta",
                "url": DE_PARA_URL,
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )
    redirect = TracingRedirect()
    opener = build_opener(redirect)
    try:
        with opener.open(
            Request(PORTAL_PAGE, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}),
            timeout=60,
        ) as response:
            if urlparse(response.url).hostname != PORTAL_HOST:
                raise ValueError("redirect externo na página De-Para")
            page_status = response.status
            url = discover_de_para_url(response.read().decode("utf-8", "replace"))
        entry = _download_validated(
            url,
            destination,
            partition_id="BR",
            validator=validate_xlsx,
        )
        attempts.append(
            {
                "rota": "pagina",
                "url": PORTAL_PAGE,
                "status_http": page_status,
                "redirects": redirect.history,
            }
        )
        return entry, attempts
    except (HTTPError, URLError, TimeoutError) as exc:
        attempts.append(
            {
                "rota": "pagina",
                "url": PORTAL_PAGE,
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )
        raise OfficialRoutesUnavailable(attempts) from exc


def partition_coverage(partition_id: str) -> tuple[str, ...]:
    """Traduz uma partição nominal conhecida em sua cobertura territorial."""

    normalized = partition_id.strip().upper().replace("-", "_")
    if normalized in UF_CODES:
        return (normalized,)
    if normalized in REGIONAL_PARTITIONS:
        return REGIONAL_PARTITIONS[normalized]
    if normalized in {"BR", "BRASIL", "NACIONAL"}:
        return UF_CODES
    raise ValueError(f"partição territorial RAIS desconhecida: {partition_id}")


def parse_archive_name(name: str, *, base_url: str = OFFICIAL_ROOT + "/") -> RaisArchive:
    """Interpreta uma partição sem afirmar qual topologia foi publicada em 2024."""

    match = re.fullmatch(
        r"RAIS_VINC_PUB_(?P<partition>[A-Z_]+?)(?:_(?P<year>\d{4}))?\.7z",
        name,
        re.I,
    )
    if not match:
        raise ValueError(f"nome .7z inesperado na listagem RAIS: {name}")
    year_text = match.group("year")
    year = int(year_text) if year_text else YEAR
    if year != YEAR:
        raise ValueError(f"nome .7z inesperado por ano incompatível: {name}")
    partition_id = match.group("partition").upper()
    covered_ufs = partition_coverage(partition_id)
    return RaisArchive(
        partition_id=partition_id,
        covered_ufs=tuple(covered_ufs),
        url=urljoin(base_url, name),
        year=year,
    )


def validate_archive_coverage(specs: list[RaisArchive]) -> dict[str, object]:
    expected = set(UF_CODES)
    filenames = [spec.filename for spec in specs]
    partition_ids = [spec.partition_id for spec in specs]
    coverage_counts: Counter[str] = Counter()
    invalid_ufs: set[str] = set()
    empty_partitions: list[str] = []

    for spec in specs:
        if not spec.covered_ufs:
            empty_partitions.append(spec.partition_id)
            continue
        for uf in spec.covered_ufs:
            if uf not in expected:
                invalid_ufs.add(uf)
            coverage_counts[uf] += 1

    covered = set(coverage_counts)
    missing = sorted(expected - covered)
    overlapping = sorted(uf for uf, count in coverage_counts.items() if count > 1)
    duplicate_files = sorted(
        filename for filename, count in Counter(filenames).items() if count > 1
    )
    duplicate_partitions = sorted(
        partition for partition, count in Counter(partition_ids).items() if count > 1
    )
    details: dict[str, object] = {
        "particoes_esperadas": partition_ids,
        "ufs_esperadas": list(UF_CODES),
        "ufs_cobertas": sorted(covered & expected),
        "ufs_ausentes": missing,
        "ufs_sobrepostas": overlapping,
        "ufs_invalidas": sorted(invalid_ufs),
        "particoes_sem_cobertura": empty_partitions,
        "arquivos_duplicados": duplicate_files,
        "particoes_duplicadas": duplicate_partitions,
    }
    errors = []
    if not specs:
        errors.append("nenhuma partição RAIS encontrada")
    if missing:
        errors.append(f"UFs ausentes: {missing}")
    if overlapping:
        errors.append(f"UFs sobrepostas: {overlapping}")
    if invalid_ufs:
        errors.append(f"UFs inválidas: {sorted(invalid_ufs)}")
    if empty_partitions:
        errors.append(f"partições sem cobertura: {empty_partitions}")
    if duplicate_files:
        errors.append(f"arquivos duplicados: {duplicate_files}")
    if duplicate_partitions:
        errors.append(f"partições duplicadas: {duplicate_partitions}")
    if errors:
        raise ArchiveCoverageError("; ".join(errors), details)
    return details


def parse_archive_listing(items: list[str], *, source_url: str) -> list[RaisArchive]:
    parsed_source = urlparse(source_url)
    if parsed_source.hostname != OFFICIAL_HOST:
        raise ValueError(f"host de listagem externo: {source_url}")
    specs: list[RaisArchive] = []
    seen_names: set[str] = set()
    for raw in items:
        parsed = urlparse(raw)
        name = Path(parsed.path or raw).name
        if parsed.hostname and parsed.hostname != OFFICIAL_HOST:
            raise ValueError(f"URL externa na listagem: {raw}")
        if not name.lower().endswith(".7z"):
            continue
        if "ESTAB" in name.upper():
            continue
        if name in seen_names:
            raise ValueError(f"entrada duplicada na listagem: {name}")
        seen_names.add(name)
        specs.append(parse_archive_name(name, base_url=OFFICIAL_ROOT + "/"))
    validate_archive_coverage(specs)
    return specs


def archives_from_listing(links: list[str]) -> list[RaisArchive]:
    return parse_archive_listing(links, source_url=OFFICIAL_ROOT + "/")


def _https_listing() -> tuple[list[str], dict[str, object]]:
    redirect = TracingRedirect()
    opener = build_opener(redirect)
    with opener.open(
        Request(OFFICIAL_ROOT + "/", headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}),
        timeout=180,
    ) as response:
        if urlparse(response.url).hostname != OFFICIAL_HOST:
            raise ValueError("redirect externo na listagem HTTPS")
        body = response.read()
        parser = _Links()
        parser.feed(body.decode("utf-8", "replace"))
        return parser.links, {
            "metodo": "HTTPS",
            "status": "success",
            "status_http": response.status,
            "url_final": response.url,
            "redirects": redirect.history,
            "listagem_sha256": hashlib.sha256(body).hexdigest(),
            "itens": len(parser.links),
        }


def _ftp_listing() -> tuple[list[str], list[dict[str, object]]]:
    attempts: list[dict[str, object]] = []
    with ftplib.FTP() as ftp:
        ftp.connect(OFFICIAL_HOST, 21, timeout=180)
        ftp.login()
        ftp.cwd(OFFICIAL_DIR)
        try:
            entries = list(ftp.mlsd())
            names = [
                name
                for name, facts in entries
                if facts.get("type") in {"file", None}
            ]
            attempts.append(
                {"metodo": "FTP MLSD", "status": "success", "itens": len(names)}
            )
        except ftplib.all_errors as exc:
            attempts.append(
                {
                    "metodo": "FTP MLSD",
                    "status": "failed",
                    "erro": f"{type(exc).__name__}: {exc}",
                }
            )
            names = ftp.nlst()
            attempts.append(
                {"metodo": "FTP NLST", "status": "success", "itens": len(names)}
            )
    return names, attempts


def discover_official_archives() -> tuple[list[RaisArchive], list[dict]]:
    attempts: list[dict[str, object]] = []
    try:
        items, evidence = _https_listing()
        attempts.append(evidence)
        return parse_archive_listing(items, source_url=OFFICIAL_ROOT + "/"), attempts
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        attempts.append(
            {
                "metodo": "HTTPS",
                "status": "failed",
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        items, ftp_attempts = _ftp_listing()
        attempts.extend(ftp_attempts)
        raw = "\n".join(items).encode()
        attempts.append(
            {
                "metodo": "FTP listagem usada",
                "status": "success",
                "listagem_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        return (
            parse_archive_listing(
                items, source_url=f"ftp://{OFFICIAL_HOST}{OFFICIAL_DIR}/"
            ),
            attempts,
        )
    except ftplib.all_errors as exc:
        attempts.append(
            {
                "metodo": "FTP",
                "status": "failed",
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )
        raise OfficialRoutesUnavailable(attempts) from exc


def _download_ftp_validated(spec: RaisArchive, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    part.unlink(missing_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(OFFICIAL_HOST, 21, timeout=180)
            ftp.login()
            with part.open("xb") as output:

                def receive(chunk: bytes) -> None:
                    nonlocal size
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)

                reply = ftp.retrbinary(
                    f"RETR {OFFICIAL_DIR}/{spec.filename}",
                    receive,
                    blocksize=8 * 1024 * 1024,
                )
        if not size:
            raise FTPTransportError("download FTP vazio")
    except (ftplib.Error, ConnectionError, TimeoutError, socket.gaierror) as exc:
        part.unlink(missing_ok=True)
        raise FTPTransportError(str(exc)) from exc
    except OSError as exc:
        part.unlink(missing_ok=True)
        if exc.errno in {
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.ETIMEDOUT,
        }:
            raise FTPTransportError(str(exc)) from exc
        raise
    try:
        validation = validate_7z(part)
        part.replace(destination)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    entry = _manifest(
        url=f"ftp://{OFFICIAL_HOST}{OFFICIAL_DIR}/{spec.filename}",
        method="FTP RETR",
        path=destination,
        partition_id=spec.partition_id,
        covered_ufs=spec.covered_ufs,
    )
    entry.update(
        resposta_ftp=reply,
        tamanho_transferido=size,
        sha256=digest.hexdigest(),
        validacao=validation,
    )
    return entry


def _download_archive(spec: RaisArchive, path: Path) -> dict[str, object]:
    attempts: list[dict[str, object]] = []
    try:
        return _download_validated(
            spec.url,
            path,
            partition_id=spec.partition_id,
            covered_ufs=spec.covered_ufs,
            validator=validate_7z,
        )
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ConnectionError,
        socket.gaierror,
    ) as exc:
        attempts.append(
            {
                "metodo": "HTTPS",
                "url": spec.url,
                "status": "failed",
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        entry = _download_ftp_validated(spec, path)
        entry["tentativas_anteriores"] = attempts
        return entry
    except FTPTransportError as exc:
        attempts.append(
            {
                "metodo": "FTP RETR",
                "url": f"ftp://{OFFICIAL_HOST}{OFFICIAL_DIR}/{spec.filename}",
                "status": "failed",
                "erro": f"{type(exc).__name__}: {exc}",
            }
        )
        raise OfficialRoutesUnavailable(attempts) from exc


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@dataclass
class RaisCollector:
    destination: Path = Path("data/raw/rais/2024")
    interim: Path = Path("data/interim/rais/2024")
    quality: Path = Path("reports/quality/mvp-demo-2026/rais")
    south_reference: Path = Path("data/processed/2026/municipios.csv")
    archives: list[RaisArchive] | None = None
    source: str = "rais"

    def collect(self) -> CollectionResult:
        entries: list[dict] = []
        artifacts: list[str] = []
        warnings: list[str] = []
        final_private = self.interim / "emprego_privado_municipal.csv"
        final_diag = self.interim / "mer_diag_01.csv"
        qa_path = self.quality / "qa.json"
        for path in (final_private, final_diag, qa_path):
            path.unlink(missing_ok=True)
        self.destination.mkdir(parents=True, exist_ok=True)
        self.quality.mkdir(parents=True, exist_ok=True)
        coverage_info: dict[str, object] = {
            "particoes_esperadas": [],
            "particoes_processadas": [],
            "ufs_esperadas": list(UF_CODES),
            "ufs_cobertas": [],
            "ufs_ausentes": list(UF_CODES),
            "ufs_sobrepostas": [],
        }

        def fail(
            status: CollectionStatus,
            error: Exception,
            extra: dict[str, object] | None = None,
        ) -> CollectionResult:
            details = dict(coverage_info)
            if isinstance(error, ArchiveCoverageError):
                details.update(error.details)
            if extra:
                details.update(extra)
            qa = {
                **details,
                "arquivos_esperados": details.get("arquivos_esperados", []),
                "arquivos_processados": details.get("arquivos_processados", []),
                "coverage_complete": False,
                "municipios_estoque_positivo": 0,
                "vinculos_privados_elegiveis": 0,
                "codigos_nao_ligados": {},
                "reconciliacao_municipal_ok": False,
                "reconciliacao_territorial_ok": False,
                "valores_invalidos": 1 if "inválid" in str(error) else 0,
                "erro": str(error),
            }
            qa_path.write_text(
                json.dumps(qa, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return CollectionResult(
                self.source,
                status,
                artifacts,
                ["MER-02", "MER-DIAG-01"],
                entries,
                warnings,
                [str(error)],
            )

        try:
            ibge_path = self.destination / "municipios-ibge.json"
            if not ibge_path.exists():

                def validate_json(path: Path) -> dict[str, object]:
                    rows = json.loads(path.read_text())
                    if not isinstance(rows, list) or not rows:
                        raise ValueError("cadastro IBGE nacional inválido")
                    return {
                        "tipo": "JSON",
                        "registros": len(rows),
                        "sha256": sha256_file(path),
                    }

                entries.append(
                    _download_validated(
                        IBGE_URL,
                        ibge_path,
                        partition_id="BR",
                        validator=validate_json,
                    )
                )
            else:
                rows = json.loads(ibge_path.read_text())
                if not isinstance(rows, list) or not rows:
                    raise ValueError("cadastro IBGE nacional inválido")
                entries.append(
                    reused_manifest(
                        ibge_path,
                        url=IBGE_URL,
                        partition_id="BR",
                        validation={
                            "tipo": "JSON",
                            "registros": len(rows),
                            "sha256": sha256_file(ibge_path),
                        },
                    )
                )
            ibge_rows = json.loads(ibge_path.read_text())
            municipality_map: dict[str, str] = {}
            for item in ibge_rows:
                code = str(item["id"])
                if not re.fullmatch(r"\d{7}", code) or code[:6] in municipality_map:
                    raise ValueError(f"cadastro IBGE inválido/ambíguo: {code}")
                municipality_map[code[:6]] = code
                municipality_map[code] = code

            south_map = load_municipality_map(self.south_reference)
            south_ids = sorted({value for key, value in south_map.items() if len(key) == 6})
            if len(south_ids) != 1191:
                raise ValueError(
                    f"universo Sul exige 1.191 municípios; obtidos {len(south_ids)}"
                )

            depara = self.destination / "De-Para Microdados.xlsx"
            if depara.exists():
                entries.append(
                    reused_manifest(
                        depara,
                        url=DE_PARA_URL,
                        partition_id="BR",
                        validation=validate_xlsx(depara),
                    )
                )
            else:
                entry, attempts = download_de_para(depara)
                entries.extend(attempts)
                entries.append(entry)
            artifacts.append(str(depara))

            specs = self.archives
            if specs is None:
                specs, attempts = discover_official_archives()
                entries.extend(attempts)
            coverage_info = validate_archive_coverage(specs)
            coverage_info["arquivos_esperados"] = [spec.filename for spec in specs]

            results = []
            processed: list[RaisArchive] = []
            for spec in specs:
                if spec.year != YEAR or urlparse(spec.url).hostname not in {
                    OFFICIAL_HOST,
                    None,
                }:
                    raise ValueError(f"arquivo fora da edição/host oficial: {spec}")
                archive = self.destination / spec.filename
                if archive.exists():
                    entries.append(
                        reused_manifest(
                            archive,
                            url=spec.url,
                            partition_id=spec.partition_id,
                            covered_ufs=spec.covered_ufs,
                            validation=validate_7z(archive),
                        )
                    )
                else:
                    entries.append(_download_archive(spec, archive))
                artifacts.append(str(archive))
                south_for_partition = [
                    code
                    for code in south_ids
                    if UF_PREFIX.get(code[:2]) in set(spec.covered_ufs)
                ]
                result = transform_archive(
                    archive,
                    allowed_ufs=spec.covered_ufs,
                    municipality_map=municipality_map,
                    year=YEAR,
                    south_municipalities=south_for_partition,
                )
                results.append(result)
                processed.append(spec)

            private = [row for result in results for row in result.private_employment]
            diagnostic = [row for result in results for row in result.diversification]
            if len(private) != len({row["municipio_id"] for row in private}):
                raise ValueError("município duplicado entre partições RAIS")
            unmatched = {
                spec.partition_id: result.quality["codigos_nao_ligados"]
                for spec, result in zip(specs, results)
                if result.quality["codigos_nao_ligados"]
            }
            reconciliations = all(
                result.quality["reconciliacao_ok"]
                and result.quality["reconciliacao_territorial_ok"]
                for result in results
            )
            if unmatched:
                raise ValueError(f"códigos municipais ativos não ligados: {unmatched}")
            if len(diagnostic) != 1191 or len(
                {row["municipio_id"] for row in diagnostic}
            ) != 1191:
                raise ValueError("MER-DIAG-01 não contém 1.191 municípios únicos")
            if not private or not reconciliations:
                raise ValueError("produto nacional vazio ou reconciliação falhou")

            municipal_reconciliation = sum(
                int(row["empregos_formais_privados"]) for row in private
            ) == sum(
                result.quality.get("vinculos_privados_elegiveis", 0)
                for result in results
            )
            if not municipal_reconciliation:
                raise ValueError("reconciliação municipal nacional falhou")

            qa = {
                "ano": YEAR,
                "particoes_esperadas": [spec.partition_id for spec in specs],
                "particoes_processadas": [spec.partition_id for spec in processed],
                "ufs_esperadas": list(UF_CODES),
                "ufs_cobertas": coverage_info["ufs_cobertas"],
                "ufs_processadas": coverage_info["ufs_cobertas"],
                "ufs_ausentes": coverage_info["ufs_ausentes"],
                "ufs_sobrepostas": coverage_info["ufs_sobrepostas"],
                "arquivos_esperados": [spec.filename for spec in specs],
                "arquivos_processados": [spec.filename for spec in processed],
                "coverage_complete": True,
                "municipios_estoque_positivo": len(private),
                "vinculos_privados_elegiveis": sum(
                    result.quality.get("vinculos_privados_elegiveis", 0)
                    for result in results
                ),
                "codigos_nao_ligados": {},
                "reconciliacao_municipal_ok": municipal_reconciliation,
                "reconciliacao_territorial_ok": reconciliations,
                "semantica_base_nacional": (
                    "esparsa; ausência equivale a zero somente com "
                    "coverage_complete=true"
                ),
            }
            self.interim.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="sit-rais-publish-", dir=self.interim.parent
            ) as directory:
                stage = Path(directory)
                _write_csv(
                    stage / final_private.name,
                    sorted(private, key=lambda row: row["municipio_id"]),
                )
                _write_csv(
                    stage / final_diag.name,
                    sorted(diagnostic, key=lambda row: row["municipio_id"]),
                )
                (stage / "qa.json").write_text(
                    json.dumps(qa, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                self.interim.mkdir(parents=True, exist_ok=True)
                (stage / final_private.name).replace(final_private)
                (stage / final_diag.name).replace(final_diag)
                (stage / "qa.json").replace(qa_path)
            artifacts.extend(map(str, (final_private, final_diag, qa_path)))
            return CollectionResult(
                self.source,
                CollectionStatus.SUCCESS,
                artifacts,
                ["MER-02", "MER-DIAG-01"],
                entries,
                warnings,
            )
        except ModuleNotFoundError as exc:
            return fail(CollectionStatus.BLOCKED_ENVIRONMENT, exc)
        except OfficialRoutesUnavailable as exc:
            entries.extend(exc.attempts)
            return fail(CollectionStatus.BLOCKED_SOURCE, exc)
        except (HTTPError, URLError, TimeoutError) as exc:
            return fail(CollectionStatus.BLOCKED_SOURCE, exc)
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            return fail(CollectionStatus.FAILED_VALIDATION, exc)


register_collector("rais", RaisCollector)
