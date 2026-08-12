"""Ponto de entrada offline do scoring e publicação do MVP.

O comando deliberadamente não inventa dados: requer uma tabela longa construída
pelos coletores, e bloqueia publicação quando o universo não é canônico.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from .scoring import DegenerateIndicator, axis_score, minmax, overall, winsorize
from .validate import validate_municipal_keys, validate_scores

DISCLAIMER = ("Esta é uma demonstração experimental do Sistema de Inteligência Territorial (SIT), "
              "construída com os eixos Infraestrutura e Conectividade e Mercado. O SIT completo prevê "
              "seis eixos. Alguns parâmetros desta demonstração foram fixados provisoriamente para "
              "testar o funcionamento do sistema de ponta a ponta e não representam decisões metodológicas definitivas.")


def run(config_path: Path, municipalities_path: Path, indicators_path: Path, output_dir: Path) -> list[dict[str, object]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    with municipalities_path.open(encoding="utf-8") as stream:
        municipalities = list(csv.DictReader(stream))
    validate_municipal_keys(municipalities, config["universo"]["municipios_esperados"])
    by_id = {row["municipio_id"]: dict(row) for row in municipalities}
    with indicators_path.open(encoding="utf-8") as stream:
        observations = list(csv.DictReader(stream))
    seen: set[tuple[str, str]] = set()
    values: dict[str, dict[str, float | None]] = defaultdict(dict)
    metadata: dict[tuple[str, str], dict[str, str]] = {}
    for row in observations:
        key = (row["municipio_id"], row["indicador_id"])
        if key in seen:
            raise ValueError(f"observação duplicada: {key}")
        seen.add(key)
        if row["municipio_id"] not in by_id:
            continue
        raw = row.get("valor_bruto", "").strip()
        values[row["indicador_id"]][row["municipio_id"]] = None if raw == "" else float(raw)
        metadata[key] = row

    ids = sorted(by_id)
    score_by_id: dict[str, dict[str, float | None]] = defaultdict(dict)
    quality: list[dict[str, object]] = []
    params: dict[str, dict[str, object]] = {}
    core = {k: v for k, v in config["indicadores"].items() if float(v["peso"]) > 0}
    for indicator, rule in core.items():
        raw_values = [values[indicator].get(key) for key in ids]
        treated, lo, hi, flags = (raw_values, None, None, [False] * len(ids))
        if not rule["limite_natural"]:
            treated, lo, hi, flags = winsorize(raw_values, *config["parametros"]["winsorizacao"])
        transformed = [None if x is None else math.log1p(x) for x in treated] if indicator in config["parametros"]["log1p"] else treated
        try:
            scores, minimum, maximum = minmax(transformed, str(rule["direcao"]))
        except (ValueError, DegenerateIndicator):
            scores, minimum, maximum = [None] * len(ids), None, None
        validate_scores(scores)
        params[indicator] = {"p1": lo, "p99": hi, "min": minimum, "max": maximum, "direcao": rule["direcao"]}
        valid = [x for x in raw_values if x is not None]
        quality.append({"indicador_id": indicator, "cobertura": len(valid) / len(ids), "ausentes": len(ids) - len(valid),
                        "zeros": sum(x == 0 for x in valid), "winsorizados": sum(flags), "min_bruto": min(valid) if valid else None,
                        "max_bruto": max(valid) if valid else None})
        for i, key in enumerate(ids):
            score_by_id[key][indicator] = scores[i]
            out = by_id[key]
            out[f"{indicator}_valor_bruto"] = raw_values[i]
            out[f"{indicator}_valor_tratado"] = treated[i]
            out[f"{indicator}_score"] = scores[i]
            out[f"{indicator}_flag"] = metadata.get((key, indicator), {}).get("flag_qualidade", "ausente") if raw_values[i] is None else ("winsorizado" if flags[i] else "observado")
            out[f"{indicator}_periodo"] = metadata.get((key, indicator), {}).get("periodo_referencia", "")

    infra_weights = {k: float(v["peso"]) for k, v in core.items() if v["eixo"] == "infra"}
    market_weights = {k: float(v["peso"]) for k, v in core.items() if v["eixo"] == "mercado"}
    for key in ids:
        infra, coverage_i = axis_score(score_by_id[key], infra_weights)
        market, coverage_m = axis_score(score_by_id[key], market_weights)
        by_id[key].update(nota_infra=infra, nota_mercado=market, cobertura_infra=coverage_i,
                          cobertura_mercado=coverage_m, nota_geral=overall(infra, market), disclaimer=DISCLAIMER)
    ranked = sorted(by_id.values(), key=lambda r: (r["nota_geral"] is None, -(r["nota_geral"] or 0), r["municipio_id"]))
    rank = 0
    uf_rank: dict[str, int] = defaultdict(int)
    for row in ranked:
        if row["nota_geral"] is not None:
            rank += 1; uf_rank[row["uf_sigla"]] += 1
            row["ranking_sul"] = rank; row["ranking_uf"] = uf_rank[row["uf_sigla"]]
        else:
            row["ranking_sul"] = row["ranking_uf"] = None
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(ranked[0])
    with (output_dir / "municipios.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(ranked)
    (output_dir / "parametros-score.json").write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "qualidade.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ranked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pontua e publica a Demonstração Experimental 2026")
    parser.add_argument("--config", type=Path, default=Path("config/edicoes/mvp-demo-2026.yml"))
    parser.add_argument("--municipios", type=Path, default=Path("data/processed/2026/municipios.csv"))
    parser.add_argument("--indicadores", type=Path, required=True, help="CSV longo: municipio_id, indicador_id, valor_bruto, período e flag")
    parser.add_argument("--output", type=Path, default=Path("data/output/mvp-demo-2026"))
    args = parser.parse_args(argv)
    run(args.config, args.municipios, args.indicadores, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
