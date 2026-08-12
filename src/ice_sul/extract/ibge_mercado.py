"""Extração reproduzível das bases oficiais do IBGE para o eixo Mercado."""

from __future__ import annotations

import hashlib
import gzip
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://servicodados.ibge.gov.br/api/v3/agregados"


@dataclass(frozen=True)
class SidraResource:
    name: str
    table: int
    period: str
    variable: int
    locations: str
    classification: str = ""

    @property
    def url(self) -> str:
        url = f"{API}/{self.table}/periodos/{self.period}/variaveis/{self.variable}?localidades={self.locations}"
        return url + (f"&classificacao={self.classification}" if self.classification else "")


AGE_18_64 = "100362,6575,6576,93087,93088,93089,93090,93091,93092,93093,93094,93095"
RESOURCES = (
    SidraResource("rdpc_censo_municipio", 10295, "2022", 13431, "N6[all]", "2[6794]|86[95251]|58[95253]"),
    SidraResource("rdpc_censo_uf", 10295, "2022", 13431, "N3[all]", "2[6794]|86[95251]|58[95253]"),
    SidraResource("rdpc_pnad_uf", 7395, "2025", 4196, "N3[all]"),
    SidraResource("populacao_municipio", 6579, "2025", 9324, "N6[all]"),
    SidraResource("populacao_18_64_censo_sul", 9514, "2022", 93, "N6[N3[41,42,43]]", f"2[6794]|287[{AGE_18_64}]|286[113635]"),
    SidraResource("pib_municipal_sul", 5938, "2021,2022,2023", 37, "N6[N3[41,42,43]]"),
    SidraResource("deflator_pib_brasil", 6784, "2021,2022,2023", 9811, "N1[all]"),
)


def download(resource: SidraResource, destination: Path, timeout: int = 120) -> dict[str, Any]:
    """Baixa uma resposta sem alterar seu conteúdo e devolve metadados de proveniência."""
    request = urllib.request.Request(resource.url, headers={"User-Agent": "SIT-MVP-2026/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        status = response.status
    if body.startswith(b"\x1f\x8b"):
        body = gzip.decompress(body)
    # Impede que mensagens de erro JSON sejam persistidas como dados válidos.
    payload = json.loads(body)
    if status != 200 or not isinstance(payload, list):
        raise RuntimeError(f"SIDRA retornou resposta inválida para {resource.name}: HTTP {status}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return {
        "name": resource.name, "table": resource.table, "period": resource.period,
        "variable": resource.variable, "url": resource.url, "http_status": status,
        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def collect_all(raw_dir: Path) -> list[dict[str, Any]]:
    return [download(r, raw_dir / f"{r.name}.json") for r in RESOURCES]
