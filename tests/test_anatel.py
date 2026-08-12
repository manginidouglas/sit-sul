import csv
from pathlib import Path

import pytest

from ice_sul.extract.anatel import AnatelCollector
from ice_sul.extract.contracts import CollectionResult
from ice_sul.extract.registry import build_collectors
from ice_sul.transform.anatel import fixed_indicators, mobile_population_indicator, parse_fixed_access
from ice_sul.transform.anatel_materialize import _canonical, _ranks, spearman

FIXTURES = Path(__file__).parent / "fixtures"


def rows(name):
    with (FIXTURES / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def by_id(result, indicator, municipality):
    return next(row for row in result if row["indicador_id"] == indicator and row["municipio_id"] == municipality)


def test_collector_is_registered_and_obeys_contract():
    collector = build_collectors(["anatel"])[0]
    assert isinstance(collector, AnatelCollector)
    assert collector.source == "anatel"
    assert CollectionResult.__annotations__["manifest_entries"]


def test_parsing_and_filters_speed_fiber_product_and_known_municipality():
    fixture = rows("anatel_fixed.csv")
    parsed = parse_fixed_access(fixture[0])
    assert parsed["municipio_id"] == "4106902"
    assert str(parsed["velocidade_mbps"]) == "100.000000"
    result = fixed_indicators(fixture, ["4106902"], "2026-06", {"4106902": 1000})
    assert by_id(result, "INF-DIG-01", "4106902")["valor_bruto"] == "8"
    assert by_id(result, "INF-DIG-02", "4106902")["valor_bruto"] == "80"
    # CNPJ: shares 0.8 and 0.2; the dedicated product does not enter the market.
    assert by_id(result, "INF-DIG-03", "4106902")["valor_bruto"] == "0.32"


def test_hhi_monopoly_zero_and_zero_denominator_missing():
    result = fixed_indicators(rows("anatel_fixed.csv"), ["4205407", "4300000"], "2026-06")
    assert by_id(result, "INF-DIG-03", "4205407")["flag_qualidade"] == "zero_observado"
    assert by_id(result, "INF-DIG-02", "4300000")["flag_qualidade"] == "ausente"
    assert by_id(result, "INF-DIG-02", "4300000")["valor_bruto"] == ""
    assert by_id(result, "INF-DIG-01", "4205407")["flag_qualidade"] == "ausente"


def test_mobile_parsing_known_municipality_zero_and_missing():
    result = mobile_population_indicator(rows("anatel_mobile.csv"), ["4106902", "4205407", "4314902"])
    assert by_id(result, "INF-DIG-04", "4106902")["valor_bruto"] == "99.75"
    assert by_id(result, "INF-DIG-04", "4205407")["flag_qualidade"] == "zero_observado"
    assert by_id(result, "INF-DIG-04", "4314902")["flag_qualidade"] == "ausente"
    assert {row["periodo_referencia"] for row in result} == {"2026-03"}


def test_invalid_schema_and_duplicate_are_rejected():
    with pytest.raises(ValueError, match="schema Anatel inválido"):
        parse_fixed_access({"Ano": "2026"})
    duplicate = [dict(rows("anatel_mobile.csv")[0]) for _ in range(2)]
    assert len(mobile_population_indicator(duplicate, ["4106902"])) == 1
    duplicate[1]["% moradores cobertos"] = "10"
    with pytest.raises(ValueError, match="divergente"):
        mobile_population_indicator(duplicate, ["4106902"])


def test_mobile_ignores_divergence_in_older_period():
    fixture = rows("anatel_mobile.csv")
    older = dict(fixture[-1])
    older["% moradores cobertos"] = "12"
    assert mobile_population_indicator(fixture + [older], ["4106902"])[0]["valor_bruto"] == "99.75"


def test_real_output_matches_canonical_universe_without_duplicates():
    canonical = Path("data/processed/2026/municipios.csv")
    output = Path("data/interim/anatel/indicadores_digitais_municipais.csv")
    ids, _ = _canonical(canonical)
    with output.open(encoding="utf-8", newline="") as stream:
        materialized = list(csv.DictReader(stream))
    keys = [(row["municipio_id"], row["indicador_id"]) for row in materialized]
    assert len(materialized) == 1191 * 3
    assert len(keys) == len(set(keys))
    assert {row["municipio_id"] for row in materialized} == set(ids)
    assert {row["indicador_id"] for row in materialized} == {"INF-DIG-02", "INF-DIG-03", "INF-DIG-04"}


def test_ranks_without_and_with_ties():
    assert _ranks({"a": 10, "b": 20, "c": 30}) == {"a": 1, "b": 2, "c": 3}
    assert _ranks({"a": 10, "b": 20, "c": 20, "d": 30}) == {
        "a": 1, "b": 2.5, "c": 2.5, "d": 4
    }


def test_spearman_identity_inverse_and_ties():
    values = {"a": 10, "b": 20, "c": 20, "d": 30}
    assert spearman(values, values) == pytest.approx(1)
    assert spearman({"a": 1, "b": 2, "c": 3}, {"a": 3, "b": 2, "c": 1}) == pytest.approx(-1)
    assert spearman(values, {"a": 1, "b": 2, "c": 3, "d": 4}) == pytest.approx(0.9486832981)
