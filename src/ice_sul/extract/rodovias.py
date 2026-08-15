"""Coleta auditável das fontes oficiais da malha rodoviária da Região Sul.

O módulo deliberadamente não consulta OSM.  URLs mudam com frequência; por isso o
catálogo é uma entrada versionada, em vez de constantes escondidas no coletor.
"""
from __future__ import annotations

import json
import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .http import download

DNIT_RAR_SHA256 = "c1db63e22f6e074bcf378d915a94a30c1f31939c6d4d68e9b19e65762f885091"
DNIT_RAR_SIZE = 78_034_601
DNIT_INNER_ZIP = "pub_202607A/02_Dados/Shapefile 202607A.zip"


def _safe_member(name: str) -> None:
    path = Path(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"membro inseguro no arquivo: {name}")


def preflight_libarchive() -> None:
    """Falha cedo se o backend declarado para RAR não estiver operacional."""
    try:
        import libarchive  # noqa: F401
        import libarchive.ffi  # noqa: F401
    except (ImportError, OSError) as exc:
        raise RuntimeError("libarchive-c e a biblioteca nativa libarchive são obrigatórios") from exc


def validate_zip(payload: bytes, *, shapefile: bool = True) -> list[str]:
    if not payload.startswith(b"PK"):
        raise ValueError("magic bytes ZIP inválidos")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        for name in names:
            _safe_member(name)
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"CRC inválido no ZIP: {corrupt}")
    if shapefile:
        suffixes = {Path(name).suffix.lower() for name in names}
        missing = {".shp", ".shx", ".dbf", ".prj"} - suffixes
        if missing:
            raise ValueError(f"componentes obrigatórios ausentes: {sorted(missing)}")
    return names


def extract_dnit_inner_zip(path: Path, *, expected_sha256: str = DNIT_RAR_SHA256,
                           expected_size: int = DNIT_RAR_SIZE) -> tuple[bytes, list[str]]:
    """Valida o RAR DNIT e devolve o ZIP aninhado, sem escrever paths do arquivo."""
    payload = path.read_bytes()
    if not payload.startswith(b"Rar!\x1a\x07"):
        raise ValueError("magic bytes RAR inválidos")
    if expected_size and len(payload) != expected_size:
        raise ValueError("tamanho do raw DNIT divergente")
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("SHA-256 do raw DNIT divergente")
    preflight_libarchive()
    inventory: list[str] = []
    inner: bytes | None = None
    import libarchive
    with libarchive.memory_reader(payload) as archive:
        for entry in archive:
            _safe_member(entry.pathname)
            inventory.append(entry.pathname)
            body = b"".join(entry.get_blocks())
            if entry.pathname.replace("\\", "/") == DNIT_INNER_ZIP:
                inner = body
    if inner is None:
        raise ValueError(f"ZIP interno ausente: {DNIT_INNER_ZIP}")
    validate_zip(inner)
    return inner, inventory


def validate_raw(path: Path, *, sha256: str | None = None, size: int | None = None) -> dict[str, Any]:
    payload = path.read_bytes(); digest = hashlib.sha256(payload).hexdigest()
    if sha256 and digest != sha256: raise ValueError("SHA-256 divergente")
    if size is not None and len(payload) != size: raise ValueError("tamanho divergente")
    return {"arquivo": str(path), "bytes": len(payload), "sha256": digest}


@dataclass(frozen=True)
class RoadSource:
    source_id: str
    institution: str
    jurisdiction: str
    states: tuple[str, ...]
    url: str
    filename: str
    reference_date: str
    alternative_urls: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RoadSource":
        return cls(
            source_id=value["source_id"], institution=value["institution"],
            jurisdiction=value["jurisdiction"], states=tuple(value["states"]),
            url=value["url"], filename=value["filename"],
            reference_date=value["reference_date"],
            alternative_urls=tuple(value.get("alternative_urls", ())),
        )


def load_catalog(path: Path) -> list[RoadSource]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = [RoadSource.from_dict(item) for item in payload["sources"]]
    ids = [item.source_id for item in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("source_id duplicado no catálogo rodoviário")
    if {uf for item in sources for uf in item.states} != {"PR", "SC", "RS"}:
        raise ValueError("catálogo não cobre exatamente PR, SC e RS")
    return sources


def collect_source(
    source: RoadSource, raw_root: Path, *,
    downloader: Callable[..., dict[str, Any]] = download,
) -> dict[str, Any]:
    """Baixa uma fonte, tentando somente alternativas da mesma instituição."""
    destination = raw_root / source.reference_date / source.source_id / source.filename
    errors: list[dict[str, str]] = []
    for url in (source.url, *source.alternative_urls):
        try:
            entry = downloader(
                url, destination, source=source.institution,
                indicators=["INF-LOG-01"], period=source.reference_date,
            )
            entry.update({
                "source_id": source.source_id,
                "jurisdicao": source.jurisdiction,
                "ufs": list(source.states), "tentativas_anteriores": errors,
            })
            manifest = destination.with_suffix(destination.suffix + ".manifest.json")
            manifest.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
            return entry
        except FileExistsError:
            raise
        except Exception as exc:  # registrar e tentar espelho oficial
            errors.append({"url": url, "erro": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(f"todas as URLs oficiais falharam para {source.source_id}: {errors}")


def collect_catalog(catalog: Path, raw_root: Path) -> list[dict[str, Any]]:
    return [collect_source(source, raw_root) for source in load_catalog(catalog)]
