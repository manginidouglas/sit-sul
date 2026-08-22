"""Cenários não congelados de acesso aéreo para avaliação na Onda 2."""
from __future__ import annotations
import math
from collections import defaultdict
from typing import Iterable, Mapping


def compare_access_scenarios(routes: Iterable[Mapping[str, object]], airports: Mapping[str, Mapping[str, float]]) -> list[dict[str, object]]:
    """Compara 90/120/180 min, aeroporto mais próximo e soma de acessíveis."""
    grouped = defaultdict(list)
    for route in routes:
        minutes = float(route["tempo_minutos"])
        if minutes >= 0 and str(route["aeroporto_id"]) in airports:
            grouped[str(route["municipio_id"])].append((minutes, airports[str(route["aeroporto_id"])]))
    output = []
    for municipality, choices in sorted(grouped.items()):
        for limit in (90, 120, 180):
            accessible = [(t, a) for t, a in choices if t <= limit]
            for metric in ("decolagens", "destinos_distintos", "score_exploratorio_frequencia_diversidade"):
                values = [(t, float(a.get(metric, a.get("score_frequencia_diversidade", 0)))) for t, a in accessible]
                output.append({"municipio_id": municipality, "limite_minutos": limit, "metrica": metric,
                               "aeroportos_acessiveis": len(values),
                               "apenas_mais_proximo": min(values, default=(0, 0))[1] if values else 0.0,
                               "soma_sem_decaimento": sum(v for _, v in values),
                               "soma_exponencial": sum(v * math.exp(-t / 60) for t, v in values)})
    return output
