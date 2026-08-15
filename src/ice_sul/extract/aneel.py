"""Coletor dos arquivos oficiais usados por DEC/FEC (ANEEL/IndQual)."""

from __future__ import annotations

import json
import hashlib
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
        manifest = self.raw_dir / "manifest.json"
        previous = {Path(item["arquivo"]).name: item for item in json.loads(manifest.read_text(encoding="utf-8"))} if manifest.exists() else {}
        for url, name in ((CONTINUIDADE_URL, "indicadores-continuidade-2020-2029.zip"), (MUNICIPIO_URL, "indqual-municipio.csv")):
            path = self.raw_dir / name
            if path.exists():
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError(f"raw existente inválido, não sobrescrito: {path}")
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if name in previous and (previous[name].get("sha256") != digest or previous[name].get("tamanho") != path.stat().st_size):
                    raise ValueError(f"raw existente diverge do manifesto e não será sobrescrito: {path}")
                entry = {"fonte": self.source, "url": url, "metodo": "GET", "periodo": "2025", "status_http": None, "content_type": None, "tamanho": path.stat().st_size, "sha256": digest, "arquivo": str(path), "licenca": "Open Data Commons ODbL", "validacao": "raw existente validado e reutilizado sem sobrescrita"}
            else:
                entry = download(url, path, source=self.source, indicators=["INF-ENE-01", "INF-ENE-02"], period="2025")
                entry.update({"licenca": "Open Data Commons ODbL", "validacao": "download não vazio; estrutura validada na materialização"})
            entries.append(entry)
            artifacts.append(str(path))
        manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts.append(str(manifest))
        return CollectionResult(self.source, CollectionStatus.SUCCESS, artifacts, ["INF-ENE-01", "INF-ENE-02"], entries)


register_collector("aneel", AneelCollector)
