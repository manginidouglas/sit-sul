"""Transforma respostas SIDRA nas bases municipais reutilizáveis do Mercado."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _number(value: Any) -> float | None:
    if value in (None, "", "-", "..", "..."):
        return None
    return float(str(value).replace(",", "."))


def sidra_records(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Achata o formato de séries da API, preservando período e localidade."""
    records: list[dict[str, Any]] = []
    for result in payload:
        for item in result.get("resultados", []):
            classifications = {c["id"]: c["categoria"] for c in item.get("classificacoes", [])}
            for series in item.get("series", []):
                locality = series["localidade"]
                for period, value in series.get("serie", {}).items():
                    records.append({"localidade_id": str(locality["id"]), "localidade_nome": locality["nome"],
                                    "periodo": str(period), "valor": _number(value),
                                    "unidade": result.get("unidade"), "classificacoes": classifications})
    return records


def load_records(path: Path) -> list[dict[str, Any]]:
    return sidra_records(json.loads(path.read_text(encoding="utf-8")))


def build_income(census_municipal: Iterable[dict[str, Any]], census_uf: Iterable[dict[str, Any]],
                 pnad_uf: Iterable[dict[str, Any]], population: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    uf_census = {r["localidade_id"]: r["valor"] for r in census_uf}
    uf_pnad = {r["localidade_id"]: r["valor"] for r in pnad_uf}
    pop = {r["localidade_id"]: r["valor"] for r in population}
    census = {r["localidade_id"]: r["valor"] for r in census_municipal}
    output = []
    for mid in sorted(census.keys() | pop.keys()):
        rdpc = census.get(mid)
        uf = mid[:2]
        values = (rdpc, uf_census.get(uf), uf_pnad.get(uf), pop.get(mid))
        estimate = None if any(v is None for v in values) or uf_census.get(uf) == 0 else rdpc / uf_census[uf] * uf_pnad[uf]
        output.append({"municipio_id": mid, "uf_codigo": uf, "periodo_censo": "2022", "periodo_corrente": "2025",
                       "rdpc_censo_municipio_reais_mes": rdpc, "rdpc_censo_uf_reais_mes": uf_census.get(uf),
                       "rdpc_pnad_uf_reais_mes": uf_pnad.get(uf), "populacao_estimada_pessoas": pop.get(mid),
                       "rdpc_est_reais_mes": estimate,
                       "massa_renda_reais_mes": None if estimate is None or pop.get(mid) is None else estimate * pop[mid]})
    return output


def build_population_18_64(age_rows: Iterable[dict[str, Any]], population_2025: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    age_sum: dict[str, float] = defaultdict(float)
    for row in age_rows:
        cats = row.get("classificacoes", {})
        if row["valor"] is not None and "Total" not in str(cats.get("287", {})):
            age_sum[row["localidade_id"]] += row["valor"]
    pop = {r["localidade_id"]: r["valor"] for r in population_2025}
    # O total censitário vem de uma consulta separada/linha total quando fornecida.
    totals: dict[str, float] = {}
    for row in age_rows:
        cats = row.get("classificacoes", {})
        if "Total" in str(cats.get("287", {})):
            totals[row["localidade_id"]] = row["valor"]
    output = []
    for mid, aged in age_sum.items():
        total = totals.get(mid)
        share = None if not total else aged / total
        current = None if share is None or pop.get(mid) is None else share * pop[mid]
        output.append({"municipio_id": mid, "periodo_estrutura": "2022", "periodo_populacao": "2025",
                       "populacao_18_64_censo_pessoas": aged, "participacao_18_64_censo": share,
                       "populacao_18_64_estimada_pessoas": current, "metodo": "estrutura etaria Censo 2022 x populacao estimada 2025"})
    return output


def build_gdp(pib_rows: Iterable[dict[str, Any]], deflator_variations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    pib: dict[str, dict[str, float]] = defaultdict(dict)
    for row in pib_rows:
        if row["valor"] is not None: pib[row["localidade_id"]][row["periodo"]] = row["valor"]
    variations = {r["periodo"]: r["valor"] for r in deflator_variations if r["valor"] is not None}
    # Índice encadeado arbitrariamente igual a 100 no primeiro ano; só a razão importa.
    index = {"2021": 100.0}
    for year in ("2022", "2023"):
        if year in variations: index[year] = index[str(int(year)-1)] * (1 + variations[year] / 100)
    output = []
    for mid, values in pib.items():
        growth = None
        if values.get("2021", 0) > 0 and "2023" in values and "2023" in index:
            growth = 100 * ((values["2023"] / values["2021"]) / (index["2023"] / index["2021"]) - 1)
        output.append({"municipio_id": mid, "indicador_id": "MER-DIAG-03", "periodo_inicial": "2021",
                       "periodo_final": "2023", "pib_2021_mil_reais": values.get("2021"),
                       "pib_2023_mil_reais": values.get("2023"), "deflator_2021_indice": index.get("2021"),
                       "deflator_2023_indice": index.get("2023"), "crescimento_real_acumulado_percentual": growth})
    return output


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows: raise ValueError("base vazia")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
