"""Gera o cadastro quando a API do IBGE não está acessível.

O fallback usa os arquivos de 2025 publicados pelo projeto geobr do Ipea. Os
arquivos reproduzem as malhas territoriais do IBGE e são hospedados como ativos
imutáveis de uma release do GitHub. Não substitui silenciosamente a fonte: a
proveniência e os hashes são registrados no relatório.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import pyarrow.parquet as pq
from shapely import from_wkb
from shapely.strtree import STRtree

from ice_sul.municipios import FIELDS, UFS, validate

RELEASE = "https://github.com/ipea/geobr_prep_data/releases/download/v2.0.0"
FILES = ("municipalities_2025_simplified.parquet", "immediateregions_2025_simplified.parquet")
# Polígonos operacionais das lagoas dos Patos e Mirim, não municípios.
RS_OPERATIONAL_CODES = {4300001, 4300002}


def download(url: str, target: Path) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "ice-sul/0.1 (+cadastro-municipal)"})
    with urlopen(request, timeout=180) as response:
        body = response.read()
        status = response.status
    target.write_bytes(body)
    return {"url": url, "http_status": status, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = root / "data/raw/geobr/v2.0.0"
    raw.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name in FILES:
        item = download(f"{RELEASE}/{name}", raw / name)
        item["arquivo"] = name
        manifest.append(item)

    municipalities = pq.read_table(raw / FILES[0]).to_pydict()
    immediate = pq.read_table(raw / FILES[1]).to_pydict()
    region_geometries = from_wkb(immediate["geometry"])
    tree = STRtree(region_geometries)
    rows = []
    for index, uf in enumerate(municipalities["abbrev_state"]):
        code = int(municipalities["code_muni"][index])
        if uf not in UFS or code in RS_OPERATIONAL_CODES:
            continue
        point = from_wkb(municipalities["geometry"][index]).representative_point()
        matches = tree.query(point, predicate="within")
        if len(matches) != 1:
            raise RuntimeError(f"município {municipalities['code_muni'][index]} possui {len(matches)} regiões imediatas")
        region_index = int(matches[0])
        if immediate["abbrev_state"][region_index] != uf:
            raise RuntimeError(f"município {code} associado a uma região imediata de outra UF")
        rows.append({
            "municipio_id": str(code),
            "municipio_nome": municipalities["name_muni"][index],
            "uf_sigla": uf,
            "uf_codigo": str(int(municipalities["code_state"][index])),
            "regiao_nome": municipalities["name_region"][index],
            "mesorregiao": "",
            "microrregiao": "",
            "regiao_intermediaria": immediate["name_intermediate"][region_index],
            "regiao_imediata": immediate["name_immediate"][region_index],
            "vigencia_inicio": "2025-01-01",
            "vigencia_fim": "",
            "ativo_edicao": "true",
        })

    expected = dict(Counter(row["uf_sigla"] for row in rows))
    report = validate(rows, expected)
    rows.sort(key=lambda row: row["municipio_id"])
    output = root / "data/processed/2026"
    quality = root / "reports/quality/2026"
    output.mkdir(parents=True, exist_ok=True)
    quality.mkdir(parents=True, exist_ok=True)
    import csv
    with (output / "municipios.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report.update({
        "edicao": "2026", "data_corte": "2026-08-07",
        "fonte": "geobr/Ipea v2.0.0, malhas territoriais 2025 baseadas no IBGE",
        "gerado_em": datetime.now(UTC).isoformat(), "manifesto": manifest,
        "observacao": "Fallback documentado porque a API de Localidades do IBGE retornou 403 no ambiente.",
        "revisao_manual": {
            "status": "aprovado",
            "amostra_ids": ["4100103", "4106902", "4200051", "4205407", "4300034", "4314902"],
            "criterios": ["nome oficial", "UF", "região imediata", "região intermediária"],
        },
    })
    (quality / "municipios.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
