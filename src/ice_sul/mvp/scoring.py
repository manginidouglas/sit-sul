"""Tratamento, normalização e agregação congelados para o MVP."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


class DegenerateIndicator(ValueError):
    pass


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if not ordered:
        raise ValueError("não há valores válidos")
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def winsorize(values: Sequence[float | None], lower: float = .01, upper: float = .99) -> tuple[list[float | None], float, float, list[bool]]:
    valid = [x for x in values if x is not None]
    lo, hi = percentile(valid, lower), percentile(valid, upper)
    treated = [None if x is None else min(max(float(x), lo), hi) for x in values]
    flags = [False if x is None else float(x) < lo or float(x) > hi for x in values]
    return treated, lo, hi, flags


def minmax(values: Sequence[float | None], direction: str) -> tuple[list[float | None], float, float]:
    valid = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    if not valid:
        raise ValueError("não há valores válidos")
    minimum, maximum = min(valid), max(valid)
    if minimum == maximum:
        raise DegenerateIndicator("min=max; indicador não pode ser pontuado")
    if direction not in {"positiva", "negativa"}:
        raise ValueError("direção inválida")
    scores = [None if x is None else min(100.0, max(0.0, 100 * ((float(x) - minimum) if direction == "positiva" else (maximum - float(x))) / (maximum - minimum))) for x in values]
    return scores, minimum, maximum


def axis_score(scores: Mapping[str, float | None], weights: Mapping[str, float], minimum_coverage: float = .8) -> tuple[float | None, float]:
    total = sum(weights.values())
    available = sum(weight for key, weight in weights.items() if scores.get(key) is not None)
    coverage = available / total if total else 0
    if available == 0 or coverage + 1e-12 < minimum_coverage:
        return None, coverage
    value = sum(weights[key] * float(scores[key]) for key in weights if scores.get(key) is not None) / available
    return value, coverage


def overall(infra: float | None, mercado: float | None, weights: Mapping[str, float] | None = None) -> float | None:
    if infra is None or mercado is None:
        return None
    weights = weights or {"infra": .5, "mercado": .5}
    total = weights["infra"] + weights["mercado"]
    return (infra * weights["infra"] + mercado * weights["mercado"]) / total
