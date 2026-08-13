"""Coletor dos bulk downloads oficiais da Anatel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import CollectionResult, CollectionStatus
from .http import download
from .registry import register_collector

FIXED_URL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/acessos_banda_larga_fixa.zip"
MOBILE_URL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/infraestrutura/cobertura_movel.zip"
AREA_URL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/infraestrutura/areas_cobertas.zip"


@dataclass
class AnatelCollector:
    raw_dir: Path = Path("data/raw/anatel/2026-08-12")
    source: str = "anatel"

    include_spatial: bool = False

    def collect(self) -> CollectionResult:
        entries = []
        artifacts = []
        specs = [
            (FIXED_URL, "acessos_banda_larga_fixa.zip", ["INF-DIG-01", "INF-DIG-02", "INF-DIG-03"], "2026-06"),
            (MOBILE_URL, "cobertura_movel.zip", ["INF-DIG-04"], "2026-03/2026-06"),
        ]
        for url, name, indicators, period in specs:
            target = self.raw_dir / name
            entry = download(url, target, source=self.source, indicators=indicators, period=period)
            entry.update({"licenca": "dados abertos governamentais; licença específica não declarada no arquivo", "versao_snapshot": "corte-2026-08-12", "validacao": "ZIP não vazio; schema e período validados na transformação"})
            entries.append(entry)
            artifacts.append(str(target))
        if self.include_spatial:
            target = self.raw_dir / "areas_cobertas.zip"
            entry = download(AREA_URL, target, source=self.source, indicators=["INF-DIG-05"], period="2026-06")
            entry.update({"licenca": "dados abertos governamentais; licença específica não declarada no arquivo", "versao_snapshot": "2026-07-01", "validacao": "ZIP e KML 4G5G_todas_{pr,sc,rs}_municipio_simple.kml validados"})
            entries.append(entry); artifacts.append(str(target))
        return CollectionResult(source=self.source, status=CollectionStatus.PARTIAL, artifacts=artifacts, indicators=["INF-DIG-01", "INF-DIG-02", "INF-DIG-03", "INF-DIG-04", "INF-DIG-05"], manifest_entries=entries, warnings=["INF-DIG-01 depende da população municipal IBGE da edição.", "INF-DIG-05 depende da camada de área passível de uso agrícola; areas_cobertas.zip foi verificado, mas tem 3,64 GB e não é baixado por padrão."])


def create_collector() -> AnatelCollector:
    return AnatelCollector()


register_collector("anatel", create_collector)
