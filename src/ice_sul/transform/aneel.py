"""Territorialização municipal dos indicadores coletivos DEC e FEC."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

PERIODO = "2025"
INDICADORES = {"DEC": "INF-ENE-01", "FEC": "INF-ENE-02"}


def parse_decimal(value: str) -> float | None:
    value = value.strip().replace(".", "").replace(",", ".")
    return None if value == "" else float(value)


def ipf(support: set[tuple[str, str]], row_margins: dict[str, float], column_margins: dict[str, float], *, tolerance: float = 1e-8, max_iterations: int = 10_000) -> tuple[dict[tuple[str, str], float], list[str]]:
    """Ajusta células positivas à margem municipal e de conjunto conhecida."""
    issues = []
    if abs(sum(row_margins.values()) - sum(column_margins.values())) > tolerance:
        issues.append(f"margens incompatíveis: municipios={sum(row_margins.values()):.6f}; conjuntos={sum(column_margins.values()):.6f}")
        return {}, issues
    cells = {edge: 1.0 for edge in support}
    if any(not any(m == row for m, _ in support) for row in row_margins) or any(not any(c == col for _, c in support) for col in column_margins):
        return {}, ["margem positiva sem célula na matriz de suporte"]
    for _ in range(max_iterations):
        for row, target in row_margins.items():
            keys = [key for key in cells if key[0] == row]
            total = sum(cells[key] for key in keys)
            for key in keys: cells[key] *= target / total
        for col, target in column_margins.items():
            keys = [key for key in cells if key[1] == col]
            total = sum(cells[key] for key in keys)
            for key in keys: cells[key] *= target / total
        error = max([abs(sum(v for (r, _), v in cells.items() if r == row) - target) for row, target in row_margins.items()] + [abs(sum(v for (_, c), v in cells.items() if c == col) - target) for col, target in column_margins.items()])
        if error <= tolerance: return cells, issues
    return {}, [f"IPF não convergiu em {max_iterations} iterações"]


def territorialize(municipalities: Iterable[str], relations: Iterable[dict[str, str]], set_values: dict[str, dict[str, float]], weights: dict[tuple[str, str], float] | None = None, *, allow_fallback: bool = True, method_level: int = 2) -> list[dict[str, object]]:
    links: dict[str, set[str]] = defaultdict(set)
    for row in relations: links[row["municipio_id"]].add(row["conjunto_id"])
    output = []
    for municipality in municipalities:
        sets = sorted(links.get(municipality, set()))
        for source_indicator, indicator_id in INDICADORES.items():
            available = [(s, set_values.get(s, {}).get(source_indicator)) for s in sets]
            available = [(s, v) for s, v in available if v is not None]
            value = None; level = None; approximate = False
            if len(sets) == 1 and len(available) == 1:
                value, level = available[0][1], 1
            elif available and len(available) == len(sets) and weights and all(weights.get((municipality, s), 0) > 0 for s, _ in available):
                denominator = sum(weights[(municipality, s)] for s, _ in available)
                value = sum(v * weights[(municipality, s)] for s, v in available) / denominator
                level = method_level
            elif allow_fallback and available and len(available) == len(sets):
                value = sum(v for _, v in available) / len(available)
                level, approximate = 4, True
            if value is not None: value = round(value, 6)
            output.append({"municipio_id": municipality, "indicador_id": indicator_id, "valor_bruto": value, "periodo_referencia": PERIODO, "flag_qualidade": "ausente" if value is None else ("territorializacao_aproximada" if approximate else "observado"), "metodo_territorializacao": None if level is None else f"nivel_{level}", "territorializacao_aproximada": approximate})
    return output


def read_annual_set_values(path: Path, year: str = PERIODO) -> dict[str, dict[str, float]]:
    totals: dict[tuple[str, str], float] = defaultdict(float); seen = set(); periods: dict[tuple[str, str], set[str]] = defaultdict(set)
    with path.open(encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream, delimiter=";"):
            indicator = row["SigIndicador"].strip(); period = row["NumPeriodoIndice"].strip()
            if row["AnoIndice"] != year or indicator not in INDICADORES: continue
            key = (row["IdeConjUndConsumidoras"], indicator, period)
            if key in seen: raise ValueError(f"duplicidade ANEEL: {key}")
            seen.add(key); value = parse_decimal(row["VlrIndiceEnviado"])
            if value is not None: totals[key[:2]] += value; periods[key[:2]].add(period)
    complete = {key: value for key, value in totals.items() if periods[key] == {str(month) for month in range(1, 13)}}
    return {set_id: {indicator: value for (candidate, indicator), value in complete.items() if candidate == set_id} for set_id in {key[0] for key in complete}}


def audit(rows: list[dict[str, object]]) -> dict[str, int]:
    methods = {f"nivel_{n}": set() for n in range(1, 5)}; missing = set()
    for row in rows:
        (missing if row["valor_bruto"] is None else methods[row["metodo_territorializacao"]]).add(row["municipio_id"])
    return {**{key: len(value) for key, value in methods.items()}, "sem_resultado": len(missing)}


def read_relations(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "latin1"):
        try:
            with path.open(encoding=encoding) as stream:
                return [{"municipio_id": row["CodMunicipio"], "conjunto_id": row["IdeConjUnidConsumidoras"]} for row in csv.DictReader(stream, delimiter=";")]
        except UnicodeDecodeError:
            continue
    raise ValueError("codificação do IndQual Município não reconhecida")


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
