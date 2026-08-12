"""Geração e comparação reproduzível dos cenários de sensibilidade."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from .pipeline import run


def ranks(values):
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    return {
        municipality_id: index + 1 for index, (municipality_id, _) in enumerate(ordered)
    }


def compare_rankings(baseline, alternative):
    baseline_ids = set(baseline)
    alternative_ids = set(alternative)
    common = sorted(baseline_ids & alternative_ids)
    entered_ranking = sorted(alternative_ids - baseline_ids)
    left_ranking = sorted(baseline_ids - alternative_ids)
    a = [baseline[key] for key in common]
    b = [alternative[key] for key in common]
    if len(common) < 2:
        rho = None
    else:
        mean_a, mean_b = statistics.fmean(a), statistics.fmean(b)
        numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
        denominator = math.sqrt(
            sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b)
        )
        rho = numerator / denominator if denominator else None
    changes = {key: abs(baseline[key] - alternative[key]) for key in common}

    def top_changes(limit):
        enters = sorted(
            key for key in common if baseline[key] > limit >= alternative[key]
        )
        enters.extend(
            sorted(key for key in entered_ranking if alternative[key] <= limit)
        )
        leaves = sorted(
            key for key in common if baseline[key] <= limit < alternative[key]
        )
        leaves.extend(sorted(key for key in left_ranking if baseline[key] <= limit))
        return {"entram": enters, "saem": leaves}

    return {
        "nota_metodologica": (
            "Spearman e mudanças ordinais consideram somente municípios rankeados "
            "nos dois cenários; entradas e saídas registram mudanças de disponibilidade."
        ),
        "n_rankeados_baseline": len(baseline_ids),
        "n_rankeados_alternativo": len(alternative_ids),
        "entraram_no_ranking": entered_ranking,
        "sairam_do_ranking": left_ranking,
        "spearman": rho,
        "mudanca_mediana": statistics.median(changes.values()) if changes else None,
        "maior_mudanca": max(changes.values(), default=None),
        "alteracoes_top20": top_changes(20),
        "alteracoes_top50": top_changes(50),
        "mais_sensiveis": sorted(changes.items(), key=lambda item: (-item[1], item[0]))[
            :20
        ],
    }


SCENARIOS = {
    "baseline": {},
    "R1_sem_winsorizacao": {"winsorization": False},
    "R2_sem_log": {"log_transform": False},
    "R3_pesos_iguais_infra": {"equal_infra_weights": True},
}


def generate_robustness(
    config_path, municipalities_path, indicators_path, output_dir, canonical_path=None
):
    """Calcula quatro vezes a mesma base, variando apenas overrides explícitos."""
    output_dir = Path(output_dir)
    scenario_results = {}
    for name, overrides in SCENARIOS.items():
        rows = run(
            Path(config_path),
            Path(municipalities_path),
            Path(indicators_path),
            output_dir / "cenarios" / name,
            Path(canonical_path) if canonical_path else None,
            **overrides,
        )
        scenario_results[name] = {
            row["municipio_id"]: {
                "nota_infra": row["nota_infra"],
                "nota_mercado": row["nota_mercado"],
                "nota_geral": row["nota_geral"],
                "ranking": row["ranking_sul"],
            }
            for row in rows
        }
    baseline_ranks = {
        key: value["ranking"]
        for key, value in scenario_results["baseline"].items()
        if value["ranking"] is not None
    }
    comparisons = {}
    for name in list(SCENARIOS)[1:]:
        alternative = {
            key: value["ranking"]
            for key, value in scenario_results[name].items()
            if value["ranking"] is not None
        }
        comparisons[name] = compare_rankings(baseline_ranks, alternative)
    payload = {"cenarios": scenario_results, "comparacoes_com_baseline": comparisons}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "robustez.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gera cenários de robustez do MVP")
    parser.add_argument(
        "--config", type=Path, default=Path("config/edicoes/mvp-demo-2026.yml")
    )
    parser.add_argument(
        "--municipios", type=Path, default=Path("data/processed/2026/municipios.csv")
    )
    parser.add_argument(
        "--canonical", type=Path, default=Path("data/processed/2026/municipios.csv")
    )
    parser.add_argument("--indicadores", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("data/output/mvp-demo-2026")
    )
    args = parser.parse_args(argv)
    generate_robustness(
        args.config, args.municipios, args.indicadores, args.output, args.canonical
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
