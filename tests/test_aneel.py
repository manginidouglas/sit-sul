import csv
import json
import zipfile
from pathlib import Path

import pytest

from ice_sul.extract.aneel import AneelCollector
from ice_sul.extract.contracts import CollectionStatus
from ice_sul.transform.aneel import PERIODO, aggregate_bdgd_rows, audit, ipf, read_annual_set_values, territorialize
from ice_sul.transform.aneel_materialize import canonical, fallback_diagnostics, materialize, validate_output


VALUES = {"a": {"DEC": 10.0, "FEC": 2.0}, "b": {"DEC": 20.0, "FEC": 4.0}}


def test_collector_contract_without_network(tmp_path, monkeypatch):
    def fake_download(url, destination, **metadata):
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(b"fixture")
        return {"url": url, "arquivo": str(destination), "periodo": metadata["period"]}
    monkeypatch.setattr("ice_sul.extract.aneel.download", fake_download)
    result = AneelCollector(tmp_path).collect()
    assert result.status == CollectionStatus.SUCCESS
    assert result.indicators == ["INF-ENE-01", "INF-ENE-02"]
    assert len(result.artifacts) == 3


def test_single_set_and_missing_are_explicit():
    rows = territorialize(["1", "2"], [{"municipio_id": "1", "conjunto_id": "a"}], VALUES)
    assert [r["valor_bruto"] for r in rows] == [10.0, 2.0, None, None]
    assert rows[0]["metodo_territorializacao"] == "nivel_1"
    assert rows[2]["flag_qualidade"] == "ausente"


def test_multiple_sets_use_known_consumer_weights_and_sum():
    relations = [{"municipio_id": "1", "conjunto_id": set_id} for set_id in ("a", "b")]
    weights = {("1", "a"): 3, ("1", "b"): 1}
    rows = territorialize(["1"], relations, VALUES, weights)
    assert rows[0]["valor_bruto"] == 12.5
    assert sum(weights.values()) == 4
    assert rows[0]["metodo_territorializacao"] == "nivel_2"


def test_ipf_reproduces_known_simple_margins():
    cells, issues = ipf({("m1", "a"), ("m1", "b"), ("m2", "a"), ("m2", "b")}, {"m1": 30, "m2": 70}, {"a": 40, "b": 60})
    assert not issues
    assert sum(v for (m, _), v in cells.items() if m == "m1") == pytest.approx(30)
    assert sum(v for (_, c), v in cells.items() if c == "b") == pytest.approx(60)


def test_ipf_records_inconsistent_margins():
    cells, issues = ipf({("m", "a")}, {"m": 2}, {"a": 3})
    assert cells == {}; assert "incompatíveis" in issues[0]


def test_absent_weights_require_explicit_fallback():
    relations = [{"municipio_id": "1", "conjunto_id": set_id} for set_id in ("a", "b")]
    assert all(r["valor_bruto"] is None for r in territorialize(["1"], relations, VALUES, allow_fallback=False))
    rows = territorialize(["1"], relations, VALUES)
    assert rows[0]["valor_bruto"] == 15
    assert rows[0]["territorializacao_aproximada"] is True
    result = audit(rows)
    assert result["por_indicador"]["INF-ENE-01"]["metodos"] == {"nivel_4": 1}
    assert result["por_indicador"]["INF-ENE-02"]["n_ausente"] == 0


def test_partial_set_values_do_not_silently_average():
    relations = [{"municipio_id": "1", "conjunto_id": set_id} for set_id in ("a", "missing")]
    assert all(r["valor_bruto"] is None for r in territorialize(["1"], relations, VALUES))


def _continuity(path: Path, rows):
    fields = ["IdeConjUndConsumidoras", "SigIndicador", "AnoIndice", "NumPeriodoIndice", "VlrIndiceEnviado"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";"); writer.writeheader(); writer.writerows(rows)


def test_parser_sums_only_full_requested_year(tmp_path):
    path = tmp_path / "source.csv"
    _continuity(path, [{"IdeConjUndConsumidoras": "a", "SigIndicador": "DEC", "AnoIndice": PERIODO, "NumPeriodoIndice": str(month), "VlrIndiceEnviado": "1,00"} for month in range(1, 13)] + [{"IdeConjUndConsumidoras": "a", "SigIndicador": "DEC", "AnoIndice": "2024", "NumPeriodoIndice": "1", "VlrIndiceEnviado": "99,0"}])
    assert read_annual_set_values(path) == {"a": {"DEC": 12.0}}


def test_parser_rejects_duplicate_period(tmp_path):
    path = tmp_path / "source.csv"; row = {"IdeConjUndConsumidoras": "a", "SigIndicador": "FEC", "AnoIndice": PERIODO, "NumPeriodoIndice": "1", "VlrIndiceEnviado": "1"}
    _continuity(path, [row, row])
    with pytest.raises(ValueError, match="duplicidade"): read_annual_set_values(path)


def test_parser_does_not_publish_incomplete_year(tmp_path):
    path = tmp_path / "source.csv"
    _continuity(path, [{"IdeConjUndConsumidoras": "a", "SigIndicador": "DEC", "AnoIndice": PERIODO, "NumPeriodoIndice": "12", "VlrIndiceEnviado": "1"}])
    assert read_annual_set_values(path) == {}


def test_zero_or_invalid_weight_falls_back_explicitly():
    relations = [{"municipio_id": "1", "conjunto_id": x} for x in ("a", "b")]
    rows = territorialize(["1"], relations, VALUES, {("1", "a"): 0, ("1", "b"): -1})
    assert {r["metodo_territorializacao"] for r in rows} == {"nivel_4"}


def test_partial_weights_for_three_sets_never_produce_level_2():
    values = {**VALUES, "c": {"DEC": 30.0, "FEC": 6.0}}
    relations = [{"municipio_id": "1", "conjunto_id": set_id} for set_id in ("a", "b", "c")]
    rows = territorialize(["1"], relations, values, {("1", "a"): 10, ("1", "b"): 20})
    assert {r["metodo_territorializacao"] for r in rows} == {"nivel_4"}
    assert all(r["territorializacao_aproximada"] for r in rows)


def test_bdgd_aggregation_real_schema_across_voltage_layers():
    layers = [
        ("UCBT_tab", [{"MUN": "4106902", "CONJ": 100, "SIT_ATIV": "AT"}, {"MUN": "4106902", "CONJ": 100, "SIT_ATIV": "AT"}, {"MUN": "4106902", "CONJ": 100, "SIT_ATIV": "IN"}]),
        ("UCMT_tab", [{"MUN": "4106902", "CONJ": "100", "SIT_ATIV": "AT"}, {"MUN": "", "CONJ": 100, "SIT_ATIV": "AT"}]),
        ("UCAT_tab", [{"MUN": "4106902", "CONJ": 101, "SIT_ATIV": "AT"}, {"MUN": "4106902", "CONJ": None, "SIT_ATIV": "AT"}]),
    ]
    weights, sources = aggregate_bdgd_rows(layers)
    assert weights == {("4106902", "100"): 3, ("4106902", "101"): 1}
    assert [source["registros_ativos"] for source in sources] == [2, 1, 1]


def test_identified_agent_with_verified_absent_bdgd_is_not_available():
    rows = territorialize(["1"], [{"municipio_id": "1", "conjunto_id": x} for x in ("1", "2")], {"1": VALUES["a"], "2": VALUES["b"]})
    catalog = {"LOCAL": {"distribuidora_identificada": True, "bdgd_catalogo_verificado": True, "bdgd_disponivel": False, "bdgd_baixada": False, "evidencia_catalogo": "consulta oficial sem resultado"}}
    result = fallback_diagnostics(rows, [{"municipio_id": "1", "municipio_nome": "X", "uf_sigla": "PR"}], [{"municipio_id": "1", "conjunto_id": x} for x in ("1", "2")], {}, {"1": {"distribuidora": "LOCAL"}, "2": {"distribuidora": "LOCAL"}}, catalog)[0]
    assert result["distribuidora_identificada"] is True
    assert result["bdgd_catalogo_verificado"] is True
    assert result["bdgd_disponivel"] is False
    assert result["motivo_nivel4"] == "bdgd_oficial_nao_disponivel"


def test_identified_agent_without_catalog_check_does_not_imply_availability():
    rows = territorialize(["1"], [{"municipio_id": "1", "conjunto_id": x} for x in ("1", "2")], {"1": VALUES["a"], "2": VALUES["b"]})
    result = fallback_diagnostics(rows, [{"municipio_id": "1", "municipio_nome": "X", "uf_sigla": "PR"}], [{"municipio_id": "1", "conjunto_id": x} for x in ("1", "2")], {}, {"1": {"distribuidora": "LOCAL"}, "2": {"distribuidora": "LOCAL"}}, {})[0]
    assert result["distribuidora_identificada"] is True
    assert result["bdgd_catalogo_verificado"] is False
    assert result["bdgd_disponivel"] is None
    assert result["motivo_nivel4"] == "nao_diagnosticado"


def test_combination_levels_and_indicator_specific_missing():
    relations = [{"municipio_id": "1", "conjunto_id": "a"}, {"municipio_id": "2", "conjunto_id": "a"}, {"municipio_id": "2", "conjunto_id": "b"}, {"municipio_id": "3", "conjunto_id": "a"}, {"municipio_id": "3", "conjunto_id": "b"}]
    values = {**VALUES, "b": {"DEC": 20.0}}
    rows = territorialize(["1", "2", "3", "4"], relations, values, {("2", "a"): 1, ("2", "b"): 2})
    assert next(r for r in rows if r["municipio_id"] == "1")["metodo_territorializacao"] == "nivel_1"
    assert next(r for r in rows if r["municipio_id"] == "2")["metodo_territorializacao"] == "nivel_2"
    result = audit(rows)
    assert result["por_indicador"]["INF-ENE-02"]["n_ausente"] == 3
    assert result["missing_ambos"] == 1


def test_zip_to_complete_canonical_output(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir(); interim = tmp_path / "interim"; report = tmp_path / "report"
    source = tmp_path / "continuity.csv"
    records = []
    for indicator in ("DEC", "FEC"):
        records += [{"IdeConjUndConsumidoras": "a", "SigIndicador": indicator, "AnoIndice": PERIODO, "NumPeriodoIndice": str(month), "VlrIndiceEnviado": "1,0"} for month in range(1, 13)]
    _continuity(source, records)
    with zipfile.ZipFile(raw / "indicadores-continuidade-2020-2029.zip", "w") as z:
        z.write(source, "indicadores-continuidade-coletivos-2020-2029.csv")
    with open("data/processed/2026/municipios.csv", encoding="utf-8") as f: municipalities = list(csv.DictReader(f))
    with (raw / "indqual-municipio.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["CodMunicipio", "IdeConjUnidConsumidoras"], delimiter=";"); writer.writeheader()
        for municipality in municipalities: writer.writerow({"CodMunicipio": municipality["municipio_id"], "IdeConjUnidConsumidoras": "a"})
    result = materialize(raw, Path("data/processed/2026/municipios.csv"), interim, report)
    with (interim / "indicadores_municipais_2025.csv").open() as f: output = list(csv.DictReader(f))
    assert len(output) == 2382 and {r["municipio_id"] for r in output} == {r["municipio_id"] for r in municipalities}
    assert result["validacoes"]["linhas"] == 2382


def test_canonical_and_output_reject_extra_or_missing(tmp_path):
    path = tmp_path / "municipios.csv"; path.write_text("municipio_id,municipio_nome,uf_sigla\n4100000,X,PR\n", encoding="utf-8")
    with pytest.raises(ValueError, match="1.191"): canonical(path)
    with pytest.raises(ValueError, match="exatamente DEC e FEC"): validate_output([], ["4100000"])


def test_existing_raw_divergent_from_manifest_is_not_overwritten(tmp_path, monkeypatch):
    raw = tmp_path / "raw"; raw.mkdir(); target = raw / "indicadores-continuidade-2020-2029.zip"; target.write_bytes(b"changed")
    (raw / "manifest.json").write_text(json.dumps([{"arquivo": str(target), "sha256": "wrong", "tamanho": 7}]))
    monkeypatch.setattr("ice_sul.extract.aneel.download", lambda *a, **k: pytest.fail("não deve baixar"))
    with pytest.raises(ValueError, match="diverge"): AneelCollector(raw).collect()
    assert target.read_bytes() == b"changed"
