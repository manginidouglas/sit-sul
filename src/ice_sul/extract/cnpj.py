"""Coleta reiniciável e auditável do bulk oficial CNPJ/RFB."""

from __future__ import annotations

import hashlib
from http.client import HTTPException, IncompleteRead, RemoteDisconnected
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .contracts import CollectionResult, CollectionStatus
from .registry import register_collector

SOURCE = "cnpj"
DEFAULT_SNAPSHOT = "2026-07"
OFFICIAL_INDEX = "https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/"
CUTOFF = "2026-08-12"
LICENSE = None
LICENSE_STATUS = "not_confirmed_in_official_material_reviewed"
PARTITIONED = ("Estabelecimentos", "Empresas")
SINGLETONS = ("Simples", "Municipios", "Naturezas")
RETRYABLE = {429, 502, 503, 504}
TRANSIENT_NETWORK_ERRORS = (
    URLError,
    TimeoutError,
    ConnectionError,
    IncompleteRead,
    RemoteDisconnected,
    HTTPException,
)
FILE_RE = re.compile(
    r"^(?:(Estabelecimentos|Empresas)(\d+)\.zip|(Simples|Municipios|Naturezas)\.zip)$",
    re.IGNORECASE,
)
CONTENT_RANGE_RE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")


class CollectionValidationError(ValueError):
    """Bytes ou metadados não satisfazem o contrato do snapshot."""


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag.lower() == "a" and href:
            self.hrefs.append(href)


def _filename(url: str) -> str:
    return Path(urlparse(url).path).name


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_zip(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1:
                raise CollectionValidationError(
                    f"ZIP deve conter exatamente um membro de dados: {path}"
                )
            corrupt = archive.testzip()
            if corrupt:
                raise CollectionValidationError(f"membro ZIP corrompido: {corrupt}")
            if members[0].file_size <= 0:
                raise CollectionValidationError(f"membro ZIP vazio: {path}")
            return {
                "zip_members": [members[0].filename],
                "uncompressed_bytes": members[0].file_size,
                "zip_validation": "single-member-crc-ok",
            }
    except zipfile.BadZipFile as exc:
        raise CollectionValidationError(f"ZIP inválido: {path}") from exc


def validate_topology(urls: list[str]) -> dict[str, list[str]]:
    """Congela topologia dinâmica, rejeitando extras, lacunas e duplicatas."""
    names = [_filename(url) for url in urls]
    folded = [name.casefold() for name in names]
    if len(folded) != len(set(folded)):
        raise CollectionValidationError("listagem contém nome de recurso duplicado")
    grouped: dict[str, list[tuple[int | None, str]]] = {}
    for url, name in zip(urls, names, strict=True):
        match = FILE_RE.fullmatch(name)
        if not match:
            raise CollectionValidationError(f"recurso inesperado: {name}")
        kind = match.group(1) or match.group(3)
        canonical = next(
            item for item in (*PARTITIONED, *SINGLETONS) if item.casefold() == kind.casefold()
        )
        grouped.setdefault(canonical, []).append(
            (int(match.group(2)) if match.group(2) is not None else None, url)
        )
    missing = [kind for kind in (*PARTITIONED, *SINGLETONS) if kind not in grouped]
    if missing:
        raise CollectionValidationError(f"recursos obrigatórios ausentes: {missing}")
    for kind in SINGLETONS:
        if len(grouped[kind]) != 1:
            raise CollectionValidationError(f"singleton {kind} não é único")
    for kind in PARTITIONED:
        indexes = sorted(index for index, _ in grouped[kind] if index is not None)
        if not indexes or indexes != list(range(indexes[-1] + 1)):
            raise CollectionValidationError(
                f"partições {kind} devem começar em 0 e ser contíguas: {indexes}"
            )
    return {
        kind: [url for _, url in sorted(entries, key=lambda item: item[0] or 0)]
        for kind, entries in grouped.items()
    }


def discover_snapshot(
    snapshot: str, *, base_url: str = OFFICIAL_INDEX, timeout: int = 60
) -> tuple[list[str], dict[str, Any]]:
    if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", snapshot):
        raise ValueError("snapshot deve usar YYYY-MM")
    index_url = urljoin(base_url.rstrip("/") + "/", snapshot + "/")
    request = Request(index_url, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        parser = _Links()
        parser.feed(body.decode("utf-8", errors="replace"))
        metadata = {
            "index_url": index_url,
            "index_final_url": response.url,
            "index_http_status": response.status,
            "index_content_type": response.headers.get("Content-Type"),
            "index_last_modified": response.headers.get("Last-Modified"),
            "discovered_at_utc": datetime.now(UTC).isoformat(),
        }
    urls = sorted(
        {
            urljoin(index_url, href)
            for href in parser.hrefs
            if FILE_RE.fullmatch(_filename(href))
        }
    )
    validate_topology(urls)
    return urls, metadata


@dataclass
class CNPJCollector:
    snapshot: str = DEFAULT_SNAPSHOT
    destination: Path | None = None
    compact_manifest: Path = Path(
        "reports/quality/mvp-demo-2026/cnpj/collection-latest.json"
    )
    base_url: str = OFFICIAL_INDEX
    timeout: int = 180
    retries: int = 3
    sleep: Any = time.sleep
    source: str = SOURCE

    def __post_init__(self) -> None:
        if self.destination is None:
            self.destination = Path("data/raw/cnpj") / self.snapshot
        else:
            self.destination = Path(self.destination)
        self.retry_evidence: list[dict[str, Any]] = []

    @property
    def operational_manifest(self) -> Path:
        assert self.destination is not None
        return self.destination / "manifest.json"

    def _with_retry(self, operation: Any) -> Any:
        for attempt in range(self.retries + 1):
            try:
                return operation()
            except HTTPError as exc:
                self.retry_evidence.append(
                    {
                        "attempt": attempt + 1,
                        "at_utc": datetime.now(UTC).isoformat(),
                        "type": type(exc).__name__,
                        "http_status": exc.code,
                        "url": exc.url,
                        "message": str(exc),
                    }
                )
                if exc.code not in RETRYABLE or attempt == self.retries:
                    raise
            except TRANSIENT_NETWORK_ERRORS as exc:
                self.retry_evidence.append(
                    {
                        "attempt": attempt + 1,
                        "at_utc": datetime.now(UTC).isoformat(),
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                if attempt == self.retries:
                    raise
            self.sleep(min(2**attempt, 30))
        raise AssertionError("retry terminou sem resultado")

    def _load_checkpoint(self) -> dict[str, Any] | None:
        if not self.operational_manifest.exists():
            return None
        try:
            manifest = json.loads(self.operational_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if manifest.get("snapshot") != self.snapshot:
            return None
        return manifest

    def _existing_entry(self, manifest: dict[str, Any], url: str) -> dict[str, Any] | None:
        return next(
            (item for item in manifest.get("artifacts", []) if item.get("url") == url),
            None,
        )

    def _receipt_path(self, target: Path) -> Path:
        return target.with_name(target.name + ".receipt.json")

    def _receipt(self, target: Path, url: str) -> dict[str, Any] | None:
        try:
            receipt = json.loads(self._receipt_path(target).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        entry = receipt.get("entry")
        if not isinstance(entry, dict) or entry.get("url") != url:
            return None
        return receipt

    def _recover_receipt(self, target: Path, url: str) -> dict[str, Any] | None:
        receipt = self._receipt(target, url)
        if not receipt:
            return None
        entry = receipt["entry"]
        part = target.with_name(target.name + ".part")
        if not target.exists() and receipt.get("state") == "validated_part" and part.exists():
            if (
                part.stat().st_size == entry.get("persisted_bytes")
                and _sha256(part) == entry.get("sha256")
            ):
                validate_zip(part)
                part.replace(target)
                _atomic_json(
                    self._receipt_path(target),
                    {"state": "promoted_recovered", "entry": entry},
                )
        return self._reuse(target, entry)

    def _reuse(self, target: Path, entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if not target.exists() or not entry:
            return None
        if (
            target.stat().st_size != entry.get("persisted_bytes")
            or _sha256(target) != entry.get("sha256")
        ):
            raise CollectionValidationError(f"raw imutável diverge do manifesto: {target}")
        zip_evidence = validate_zip(target)
        return {
            **entry,
            **zip_evidence,
            "reused": True,
            "transferred_bytes": 0,
            "validated_at_utc": datetime.now(UTC).isoformat(),
        }

    def _partial_identity(self, part_meta: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(part_meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if value.get("etag") or value.get("last_modified") else None

    def _download_once(self, url: str, target: Path) -> dict[str, Any]:
        part = target.with_name(target.name + ".part")
        part_meta = target.with_name(target.name + ".part.json")
        identity = self._partial_identity(part_meta) if part.exists() else None
        offset = part.stat().st_size if identity else 0
        if part.exists() and not identity:
            part.unlink()
            part_meta.unlink(missing_ok=True)
        headers = {"User-Agent": "SIT-mvp-demo-2026/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            headers["If-Range"] = identity["etag"] or identity["last_modified"]
        request = Request(url, headers=headers)
        with urlopen(request, timeout=self.timeout) as response:
            status = response.status
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
            content_range = response.headers.get("Content-Range")
            total: int | None = None
            resume = False
            if offset:
                match = CONTENT_RANGE_RE.fullmatch(content_range or "")
                same_validator = (
                    (identity.get("etag") and etag == identity["etag"])
                    or (
                        not identity.get("etag")
                        and identity.get("last_modified")
                        and last_modified == identity["last_modified"]
                    )
                )
                if status == 206 and match and int(match.group(1)) == offset and same_validator:
                    total = int(match.group(3))
                    resume = True
                else:
                    part.unlink(missing_ok=True)
                    part_meta.unlink(missing_ok=True)
                    offset = 0
                    if status == 206:
                        raise CollectionValidationError(
                            "resposta parcial não comprova identidade/offset; reinicie o recurso"
                        )
            if not resume:
                if status != 200:
                    raise CollectionValidationError(f"download novo esperava HTTP 200, recebeu {status}")
                length = response.headers.get("Content-Length")
                total = int(length) if length and length.isdigit() else None
            current_identity = {
                "url": url,
                "etag": etag,
                "last_modified": last_modified,
                "expected_total_bytes": total,
            }
            _atomic_json(part_meta, current_identity)
            transferred = 0
            with part.open("ab" if resume else "wb") as output:
                while True:
                    try:
                        block = response.read(1024 * 1024)
                    except IncompleteRead as exc:
                        if exc.partial:
                            output.write(exc.partial)
                            transferred += len(exc.partial)
                        raise
                    if not block:
                        break
                    output.write(block)
                    transferred += len(block)
            persisted = part.stat().st_size
            if total is not None and persisted != total:
                raise URLError(f"transferência incompleta: {persisted}/{total}")
            metadata = {
                "http_status": status,
                "final_url": response.url,
                "redirects": [] if response.url == url else [response.url],
                "content_type": response.headers.get("Content-Type"),
                "content_length": response.headers.get("Content-Length"),
                "content_range": content_range,
                "etag": etag,
                "last_modified": last_modified,
                "resumed_from_bytes": offset if resume else 0,
                "transferred_bytes_this_attempt": transferred,
            }
        zip_evidence = validate_zip(part)
        digest = _sha256(part)
        collected_at = datetime.now(UTC).isoformat()
        entry = {
            "source": SOURCE,
            "url": url,
            "method": "GET",
            "parameters": {},
            "name": target.name,
            "snapshot": self.snapshot,
            "period_reference": self.snapshot,
            "collected_at_utc": collected_at,
            "path": str(target),
            "logical_path": str(target),
            **metadata,
            "transferred_bytes": transferred,
            "persisted_bytes": part.stat().st_size,
            "sha256": digest,
            "license": LICENSE,
            "license_status": LICENSE_STATUS,
            **zip_evidence,
            "reused": False,
            "validated_at_utc": collected_at,
        }
        receipt = self._receipt_path(target)
        _atomic_json(receipt, {"state": "validated_part", "entry": entry})
        part.replace(target)
        _atomic_json(receipt, {"state": "promoted", "entry": entry})
        part_meta.unlink(missing_ok=True)
        return entry

    def _download(self, url: str, manifest: dict[str, Any]) -> dict[str, Any]:
        assert self.destination is not None
        self.destination.mkdir(parents=True, exist_ok=True)
        target = self.destination / _filename(url)
        provenance = self._existing_entry(manifest, url)
        reused = self._reuse(target, provenance) if provenance else self._recover_receipt(target, url)
        if reused:
            return reused
        if target.exists():
            raise CollectionValidationError(f"raw sem proveniência não pode ser sobrescrito: {target}")
        return self._with_retry(lambda: self._download_once(url, target))

    def _head_size(self, url: str) -> int | None:
        request = Request(
            url,
            method="HEAD",
            headers={"User-Agent": "SIT-mvp-demo-2026/1.0"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                length = response.headers.get("Content-Length")
                return int(length) if length and length.isdigit() else None
        except (HTTPError, *TRANSIENT_NETWORK_ERRORS):
            return None

    def _storage_preflight(self, urls: list[str]) -> dict[str, Any]:
        assert self.destination is not None
        self.destination.mkdir(parents=True, exist_ok=True)
        sizes = {url: self._head_size(url) for url in urls}
        known = [value for value in sizes.values() if value is not None]
        raw_bytes = sum(known)
        # Pico de coleta: raws comprimidos + maior .part + reserva inicial de
        # 8 GiB para scratch e 1 GiB de margem. Após baixar, a transformação
        # recalcula scratch com tamanhos descomprimidos reais do ZIP.
        largest = max(known, default=0)
        required = (
            raw_bytes + largest + 9 * 1024**3
            if len(known) == len(urls)
            else None
        )
        free = shutil.disk_usage(self.destination.parent).free
        evidence = {
            "content_length_by_url": sizes,
            "all_content_lengths_known": len(known) == len(urls),
            "estimated_raw_bytes": raw_bytes if known else None,
            "largest_partial_bytes": largest if known else None,
            "estimated_required_bytes_raw_scratch_staging": required,
            "free_bytes": free,
            "formula": "raw + largest .part + 8 GiB scratch reserve + 1 GiB margin",
        }
        if required is not None and required > free:
            raise OSError(
                f"espaço insuficiente: necessários {required} bytes, livres {free}"
            )
        return evidence

    def collect(self) -> CollectionResult:
        self.retry_evidence = []
        manifest = self._load_checkpoint() or {
            "source": SOURCE,
            "snapshot": self.snapshot,
            "status": "partial",
            "coverage_complete": False,
            "cutoff": CUTOFF,
            "license": LICENSE,
            "license_status": LICENSE_STATUS,
            "artifacts": [],
        }
        manifest.update(
            source=SOURCE,
            snapshot=self.snapshot,
            cutoff=CUTOFF,
            license=LICENSE,
            license_status=LICENSE_STATUS,
        )
        try:
            urls, discovery = self._with_retry(
                lambda: discover_snapshot(
                    self.snapshot, base_url=self.base_url, timeout=self.timeout
                )
            )
            topology = validate_topology(urls)
            manifest.update(discovery)
            manifest["topology"] = {
                kind: [_filename(url) for url in values] for kind, values in topology.items()
            }
            manifest["expected_artifact_count"] = len(urls)
            manifest["storage_preflight"] = self._storage_preflight(urls)
            _atomic_json(self.operational_manifest, manifest)
            completed: list[dict[str, Any]] = []
            for url in urls:
                entry = self._download(url, manifest)
                completed.append(entry)
                manifest["artifacts"] = completed
                manifest["completed_artifact_count"] = len(completed)
                _atomic_json(self.operational_manifest, manifest)
            manifest.update(
                status="complete",
                coverage_complete=True,
                completed_at_utc=datetime.now(UTC).isoformat(),
            )
            _atomic_json(self.operational_manifest, manifest)
            _atomic_json(self.compact_manifest, manifest)
            return CollectionResult(
                source=SOURCE,
                status=CollectionStatus.SUCCESS,
                artifacts=[str(self.operational_manifest)],
                indicators=["MER-DIAG-02"],
                manifest_entries=completed,
            )
        except HTTPError as exc:
            if exc.code in {401, 403}:
                status = CollectionStatus.BLOCKED_SOURCE
            elif exc.code in RETRYABLE:
                status = CollectionStatus.UNAVAILABLE
            else:
                status = CollectionStatus.ENDPOINT_REVIEW
            evidence = {"type": type(exc).__name__, "http_status": exc.code, "message": str(exc)}
        except TRANSIENT_NETWORK_ERRORS as exc:
            status = CollectionStatus.UNAVAILABLE
            evidence = {"type": type(exc).__name__, "message": str(exc)}
        except PermissionError as exc:
            status = CollectionStatus.BLOCKED_ENVIRONMENT
            evidence = {"type": type(exc).__name__, "message": str(exc)}
        except (CollectionValidationError, ValueError) as exc:
            status = CollectionStatus.FAILED_VALIDATION
            evidence = {"type": type(exc).__name__, "message": str(exc)}
        except OSError as exc:
            status = CollectionStatus.BLOCKED_ENVIRONMENT
            evidence = {"type": type(exc).__name__, "message": str(exc)}
        evidence["at_utc"] = datetime.now(UTC).isoformat()
        manifest.update(
            status="partial",
            coverage_complete=False,
            failure=evidence,
            attempts=self.retry_evidence or [evidence],
        )
        try:
            _atomic_json(self.operational_manifest, manifest)
            _atomic_json(self.compact_manifest, manifest)
        except OSError as write_exc:
            status = CollectionStatus.BLOCKED_ENVIRONMENT
            evidence["manifest_write_failure"] = str(write_exc)
        return CollectionResult(
            source=SOURCE,
            status=status,
            artifacts=[str(self.operational_manifest)] if self.operational_manifest.exists() else [],
            indicators=["MER-DIAG-02"],
            manifest_entries=manifest.get("artifacts", []),
            errors=[evidence["message"]],
        )


register_collector(SOURCE, CNPJCollector)
