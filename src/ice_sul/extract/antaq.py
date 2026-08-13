"""Coleta e valida os dois recursos oficiais usados pelo INF-LOG-04."""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError

from .contracts import CollectionResult, CollectionStatus
from .http import download
from .registry import register_collector

SOURCE = "ANTAQ"
INDICATORS = ["INF-LOG-04"]
INSTALLATIONS_URL = "https://www.gov.br/antaq/pt-br/central-de-conteudos/Instalaesporturias06052025.zip"
YEARBOOK_URL = "https://www.gov.br/antaq/pt-br/central-de-conteudos/publicacoes-da-antaq/Anuario2025.pdf"


def validate_installations_zip(path: Path) -> None:
    if path.read_bytes()[:4] != b"PK\x03\x04":
        raise ValueError("recurso de instalações não possui magic bytes ZIP")
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP de instalações corrompido")
            names = [name.lower() for name in archive.namelist()]
            if not any(name.endswith("portos.xlsx") for name in names):
                raise ValueError("ZIP oficial não contém Portos.xlsx")
            if not any(name.endswith("portos.dbf") for name in names):
                raise ValueError("ZIP oficial não contém Portos.dbf")
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP de instalações inválido") from exc


def validate_yearbook_pdf(path: Path) -> None:
    payload = path.read_bytes()
    if not payload.startswith(b"%PDF-"):
        raise ValueError("recurso do Anuário não possui magic bytes PDF")
    if len(payload) < 100_000 or b"%%EOF" not in payload[-2048:]:
        raise ValueError("PDF do Anuário truncado ou de tamanho implausível")


@dataclass
class AntaqCollector:
    installations_url: str = INSTALLATIONS_URL
    yearbook_url: str = YEARBOOK_URL
    installations_path: Path = Path("data/raw/antaq/instalacoes-portuarias-2025-05-06.zip")
    yearbook_path: Path = Path("data/raw/antaq/Anuario2025.pdf")
    source: str = "antaq"

    def collect(self) -> CollectionResult:
        entries = []
        resources = (
            (self.installations_url, self.installations_path, "cadastro geográfico 2025-05-06", validate_installations_zip),
            (self.yearbook_url, self.yearbook_path, "ano completo 2025", validate_yearbook_pdf),
        )
        try:
            for url, path, period, validator in resources:
                entry = download(url, path, source=SOURCE, indicators=INDICATORS, period=period)
                validator(path)
                entry["validacao"] = "formato e conteúdo estrutural validados"
                entries.append(entry)
        except HTTPError as exc:
            status = CollectionStatus.BLOCKED_SOURCE if exc.code in {401, 403} else CollectionStatus.ENDPOINT_REVIEW
            return CollectionResult(source=self.source, status=status, indicators=INDICATORS, manifest_entries=entries, errors=[f"HTTP {exc.code}"])
        except (URLError, TimeoutError) as exc:
            return CollectionResult(source=self.source, status=CollectionStatus.BLOCKED_ENVIRONMENT, indicators=INDICATORS, manifest_entries=entries, errors=[str(exc)])
        except (ValueError, FileExistsError, OSError) as exc:
            return CollectionResult(source=self.source, status=CollectionStatus.FAILED_VALIDATION, indicators=INDICATORS, manifest_entries=entries, errors=[str(exc)])
        return CollectionResult(source=self.source, status=CollectionStatus.SUCCESS, artifacts=[str(self.installations_path), str(self.yearbook_path)], indicators=INDICATORS, manifest_entries=entries)

    @staticmethod
    def write_result(result: CollectionResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


register_collector("antaq", AntaqCollector)


def main() -> None:
    """Obtém raws ausentes e valida formatos e hashes oficiais conhecidos."""
    import hashlib
    expected = {
        Path("data/raw/antaq/instalacoes-portuarias-2025-05-06.zip"): (INSTALLATIONS_URL, "79e28332bdd031388a6f2305e4f1e2e741c057a64a63724ea4278f78a040fb63", validate_installations_zip),
        Path("data/raw/antaq/Anuario2025.pdf"): (YEARBOOK_URL, "75a258baeb9267d1cf1c0be8b9353aa31850b950b55197e79b9072e484961e2e", validate_yearbook_pdf),
    }
    for path, (url, sha256, validator) in expected.items():
        if not path.exists():
            download(url, path, source=SOURCE, indicators=INDICATORS, period="2025")
        validator(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise ValueError(f"SHA-256 oficial divergente: {path}")
        print(f"validado: {path}")


if __name__ == "__main__":
    main()
