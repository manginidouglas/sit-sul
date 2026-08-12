"""Coletor dos arquivos oficiais usados por DEC/FEC (ANEEL/IndQual)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import CollectionResult, CollectionStatus
from .http import download
from .registry import register_collector

CONTINUIDADE_URL = "https://dadosabertos.aneel.gov.br/dataset/d5f0712e-62f6-4736-8dff-9991f10758a7/resource/4493985c-baea-429c-9df5-3030422c71d7/download/indicadores-continuidade-coletivos-2020-2029.zip"
MUNICIPIO_URL = "https://dadosabertos.aneel.gov.br/dataset/db9c9f60-b3b5-4504-9dfe-2637922d53ce/resource/3f841488-80a8-42f2-a6ca-e0c593b228de/download/indqual-municipio.csv"


@dataclass
class AneelCollector:
    raw_dir: Path = Path("data/raw/aneel")
    source: str = "aneel"

    def collect(self) -> CollectionResult:
        entries = []
        artifacts = []
        for url, name in ((CONTINUIDADE_URL, "indicadores-continuidade-2020-2029.zip"), (MUNICIPIO_URL, "indqual-municipio.csv")):
            path = self.raw_dir / name
            entries.append(download(url, path, source=self.source, indicators=["INF-ENE-01", "INF-ENE-02"], period="2025"))
            artifacts.append(str(path))
        manifest = self.raw_dir / "manifest.json"
        manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts.append(str(manifest))
        return CollectionResult(self.source, CollectionStatus.SUCCESS, artifacts, ["INF-ENE-01", "INF-ENE-02"], entries)


register_collector("aneel", AneelCollector)
