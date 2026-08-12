"""Materialização reproduzível dos produtos reais da Anatel (stdlib only)."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
import io
import json
from pathlib import Path
import re
from statistics import mean, median
import zipfile

from .anatel import OUTPUT_COLUMNS, fixed_snapshot, mobile_population_indicator


def _canonical(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = [row["municipio_id"] for row in rows]
    if len(ids) != 1191 or len(set(ids)) != 1191 or {row["uf_sigla"] for row in rows} != {"PR", "SC", "RS"}:
        raise ValueError("universo canônico deve conter exatamente 1.191 códigos únicos de PR/SC/RS")
    return ids, {row["municipio_id"]: row for row in rows}


def _municipal_member(archive: zipfile.ZipFile, cutoff: str) -> tuple[str, list[str]]:
    found = []
    for name in archive.namelist():
        match = re.fullmatch(r"Cobertura_(\d{4})_(\d{2})_Municipios\.csv", name)
        if match:
            period = f"{match[1]}-{match[2]}"
            if period <= cutoff:
                found.append((period, name))
    if not found:
        raise ValueError("ZIP sem snapshot municipal de cobertura até o corte")
    return max(found)[1], [period for period, _ in sorted(found)]


def _percentile(values: list[float], percentage: int) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * percentage / 100
    lower = int(position)
    fraction = position - lower
    return values[lower] if fraction == 0 else values[lower] + fraction * (values[lower + 1] - values[lower])


def _stats(rows: list[dict[str, object]]) -> dict[str, object]:
    values = sorted(float(row["valor_bruto"]) for row in rows if row["valor_bruto"] != "")
    flags = {flag: sum(row["flag_qualidade"] == flag for row in rows) for flag in ("observado", "zero_observado", "ausente")}
    return {**flags, "cobertura_percentual": round(100 * (flags["observado"] + flags["zero_observado"]) / 1191, 6), "minimo": min(values) if values else None, "p1": _percentile(values, 1), "p5": _percentile(values, 5), "mediana": median(values) if values else None, "p95": _percentile(values, 95), "p99": _percentile(values, 99), "maximo": max(values) if values else None, "fora_faixa": sum(not 0 <= value <= 100 for value in values), "periodo": next(iter({str(row["periodo_referencia"]) for row in rows}))}


def _ranks(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values, key=values.get)
    return {municipality: float(rank) for rank, municipality in enumerate(ordered, 1)}


def materialize(fixed_zip: Path, mobile_zip: Path, canonical_csv: Path, output_dir: Path) -> dict[str, object]:
    ids, municipalities = _canonical(canonical_csv)
    with zipfile.ZipFile(fixed_zip) as archive:
        with archive.open("Acessos_Banda_Larga_Fixa_2026_Colunas.csv") as raw:
            fixed, comparison = fixed_snapshot(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter=";"), ids, "2026-06")
    with zipfile.ZipFile(mobile_zip) as archive:
        member, available_periods = _municipal_member(archive, "2026-08")
        with archive.open(member) as raw:
            mobile = mobile_population_indicator(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter=";"), ids)

    published = [row for row in fixed if row["indicador_id"] in {"INF-DIG-02", "INF-DIG-03"}] + mobile
    keys = [(str(row["municipio_id"]), str(row["indicador_id"])) for row in published]
    if len(published) != 3 * 1191 or len(set(keys)) != len(keys) or {key[0] for key in keys} != set(ids):
        raise ValueError("output não coincide exatamente com o universo canônico")
    output_dir.mkdir(parents=True, exist_ok=True)
    columns = list(OUTPUT_COLUMNS) + ["acessos_fibra", "total_acessos_internet", "prestadores_cnpj"]
    with (output_dir / "indicadores_digitais_municipais.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader(); writer.writerows(published)
    numerator = [row for row in fixed if row["indicador_id"] == "INF-DIG-01-NUM"]
    with (output_dir / "inf-dig-01_numerador.csv").open("w", encoding="utf-8", newline="") as stream:
        columns_num = list(OUTPUT_COLUMNS) + ["acessos_ge_100_mbps", "total_acessos_internet"]
        writer = csv.DictWriter(stream, fieldnames=columns_num, extrasaction="ignore", lineterminator="\n"); writer.writeheader(); writer.writerows(numerator)
    comparison_rows = comparison[:-1]
    with (output_dir / "inf-dig-03_unidades_exploratorias.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=comparison[0], lineterminator="\n"); writer.writeheader(); writer.writerows(comparison)

    usable = [row for row in comparison_rows if row["diferenca_absoluta"] != ""]
    cnpj = {str(row["municipio_id"]): float(row["competitividade_cnpj"]) for row in usable}
    hybrid = {str(row["municipio_id"]): float(row["competitividade_hibrida"]) for row in usable}
    rc, rh = _ranks(cnpj), _ranks(hybrid)
    correlation = 1 - 6 * sum((rc[mid] - rh[mid]) ** 2 for mid in rc) / (len(rc) * (len(rc) ** 2 - 1))
    differences = sorted(float(row["diferenca_absoluta"]) for row in usable)
    largest = sorted(usable, key=lambda row: float(row["diferenca_absoluta"]), reverse=True)[:10]
    qa = {
        "gerado_em_utc": datetime.now(UTC).isoformat(),
        "universo": 1191,
        "periodos_municipais_cobertura_disponiveis": available_periods,
        "indicadores": {indicator: _stats([row for row in published if row["indicador_id"] == indicator]) for indicator in ("INF-DIG-02", "INF-DIG-03", "INF-DIG-04")},
        "comparacao_inf_dig_03": {"municipios": len(usable), "correlacao_spearman_ranking": correlation, "media_diferenca_absoluta": mean(differences), "mediana_diferenca_absoluta": median(differences), "p95_diferenca_absoluta": _percentile(differences, 95), "p99_diferenca_absoluta": _percentile(differences, 99), "cnpjs_em_grupos_informativos": comparison[-1]["cnpjs"], "grupos_informativos": comparison[-1]["unidades_hibridas"], "maiores_diferencas": largest},
    }
    selected = ["4106902", "4205407", "4314902", "4100103", "4200051", "4300034"]
    qa["sanity_checks"] = [{"municipio_id": mid, "municipio": municipalities[mid]["municipio_nome"], "uf": municipalities[mid]["uf_sigla"], "resultados": [row for row in published if row["municipio_id"] == mid]} for mid in selected]
    (output_dir / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return qa


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("fixed_zip", type=Path); parser.add_argument("mobile_zip", type=Path)
    parser.add_argument("--municipios", type=Path, default=Path("data/processed/2026/municipios.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/anatel"))
    args = parser.parse_args()
    materialize(args.fixed_zip, args.mobile_zip, args.municipios, args.output)
