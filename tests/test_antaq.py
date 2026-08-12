from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import pytest

from ice_sul.extract.antaq import AntaqCollector
from ice_sul.extract.contracts import CollectionStatus
from ice_sul.transform.antaq import build_eligible_installations, latest_complete_window


def movements():
    rows = []
    for year, months in ((2025, range(8, 13)), (2026, range(1, 8))):
        for month in months:
            rows.append({"instalacao_id": "BRPNG", "periodo": f"{year}-{month:02}", "movimentacao_t": "10", "natureza_carga": "Granel sólido"})
    rows += [
        {"instalacao_id": "TUP-GERAL", "periodo": "2026-07", "movimentacao_t": "0.1", "natureza_carga": "Carga Geral"},
        {"instalacao_id": "TUP-BULK", "periodo": "2026-07", "movimentacao_t": "999", "natureza_carga": "Granel líquido"},
    ]
    return rows


def installations():
    return [
        {"instalacao_id": "BRPNG", "nome": "Porto de Paranaguá", "tipo": "Porto Organizado", "latitude": "-25.50", "longitude": "-48.52", "referencia_coordenada": "centroide"},
        {"instalacao_id": "TUP-GERAL", "nome": "Terminal Geral", "tipo": "TUP", "latitude": "-26", "longitude": "-48", "referencia_coordenada": "acesso terrestre"},
        {"instalacao_id": "TUP-BULK", "nome": "Terminal Graneleiro", "tipo": "Terminal de Uso Privado", "latitude": "-30", "longitude": "-51", "referencia_coordenada": "centro geométrico"},
        {"instalacao_id": "SEM-MOV", "nome": "Cadastro sem operação", "tipo": "TUP", "latitude": "-29", "longitude": "-49", "referencia_coordenada": "centroide"},
    ]


def test_window_uses_latest_complete_12_months():
    assert latest_complete_window(movements()) == (date(2025, 8, 1), date(2026, 7, 31))


def test_frozen_eligibility_and_no_minimum_tonnage():
    by_id = {row["instalacao_id"]: row for row in build_eligible_installations(installations(), movements())}
    assert by_id["BRPNG"]["elegivel"] is True
    assert by_id["BRPNG"]["movimentacao_t"] == "120"
    assert by_id["TUP-GERAL"]["elegivel"] is True
    assert by_id["TUP-BULK"]["elegivel"] is False
    assert by_id["SEM-MOV"]["elegivel"] is False
    assert by_id["BRPNG"]["ajuste_acesso_terrestre_onda2"] is True
    assert by_id["TUP-GERAL"]["ajuste_acesso_terrestre_onda2"] is False


def test_rejects_conflicting_duplicate_installation():
    duplicate = installations() + [{**installations()[0], "nome": "Outro porto"}]
    with pytest.raises(ValueError, match="duplicidade cadastral conflitante"):
        build_eligible_installations(duplicate, movements())


def test_rejects_missing_month_in_window():
    with pytest.raises(ValueError, match="janela incompleta"):
        build_eligible_installations(installations(), [row for row in movements() if row["periodo"] != "2025-09"])


def test_collector_maps_503_to_endpoint_review(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise HTTPError("https://example", 503, "Unavailable", {}, None)
    monkeypatch.setattr("ice_sul.extract.antaq.download", unavailable)
    result = AntaqCollector(resource_url="https://example", raw_path=tmp_path / "raw").collect()
    assert result.status == CollectionStatus.ENDPOINT_REVIEW
    assert "não demonstra indisponibilidade" in result.warnings[0]


def test_collector_runs_offline_with_fixture(monkeypatch, tmp_path):
    def fixture_download(url, destination, **kwargs):
        destination.write_bytes(Path("tests/fixtures/antaq/sample.txt").read_bytes())
        return {"url": url, "arquivo": str(destination), "sha256": "fixture"}
    monkeypatch.setattr("ice_sul.extract.antaq.download", fixture_download)
    result = AntaqCollector(resource_url="fixture://antaq", raw_path=tmp_path / "raw").collect()
    assert result.status == CollectionStatus.SUCCESS
    assert result.manifest_entries[0]["sha256"] == "fixture"
