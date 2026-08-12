import csv
from pathlib import Path

import pytest

from ice_sul.extract.aneel import AneelCollector
from ice_sul.extract.contracts import CollectionStatus
from ice_sul.transform.aneel import PERIODO, audit, ipf, read_annual_set_values, territorialize


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
    assert audit(rows) == {"nivel_1": 0, "nivel_2": 0, "nivel_3": 0, "nivel_4": 1, "sem_resultado": 0}


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
