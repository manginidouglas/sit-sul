import json
from pathlib import Path

import pytest

from ice_sul.municipios import Download, ValidationError, build, normalize, validate


FIXTURE = Path(__file__).parent / "fixtures" / "ibge_municipios.json"


def rows():
    return [normalize(item, vigencia_inicio="2026-01-01") for item in json.loads(FIXTURE.read_text())]


def test_normaliza_hierarquia_e_preserva_codigo_como_texto():
    result = rows()[0]
    assert result["municipio_id"] == "4100103"
    assert result["uf_sigla"] == "PR"
    assert result["regiao_intermediaria"] == "Londrina"
    assert result["regiao_imediata"] == "Santo Antônio da Platina"


def test_valida_unicidade_ufs_e_contagens_obtidas_da_fonte():
    report = validate(rows(), {"PR": 1, "SC": 1, "RS": 1})
    assert report["status"] == "aprovado"
    assert report["total"] == 3


@pytest.mark.parametrize("mutation", ["duplicado", "vazio", "uf_invalida", "contagem"])
def test_bloqueia_cadastro_invalido(mutation):
    data = rows()
    expected = {"PR": 1, "SC": 1, "RS": 1}
    if mutation == "duplicado":
        data[1]["municipio_id"] = data[0]["municipio_id"]
    elif mutation == "vazio":
        data[0]["municipio_nome"] = ""
    elif mutation == "uf_invalida":
        data[0]["uf_sigla"] = "SP"
    else:
        expected["PR"] = 2
    with pytest.raises(ValidationError):
        validate(data, expected)


def test_pipeline_publica_csv_relatorio_e_brutos(monkeypatch, tmp_path):
    fixture = FIXTURE.read_bytes()
    by_uf = {item["microrregiao"]["mesorregiao"]["UF"]["sigla"]: item
             for item in json.loads(fixture)}

    def fake_fetch(url, uf):
        body = json.dumps([by_uf[uf]], ensure_ascii=False).encode()
        return Download(uf, url, body, "2026-08-07T00:00:00+00:00")

    monkeypatch.setattr("ice_sul.municipios.fetch", fake_fetch)
    csv_path, report_path = build(edition="2026", cutoff="2026-08-07",
        valid_from="2026-01-01", url_template="https://example.test/{uf}", root=tmp_path)

    assert csv_path.read_text(encoding="utf-8").count("\n") == 4
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "aprovado"
    assert len(report["manifesto"]) == 3
    assert (tmp_path / "data/raw/ibge_localidades/2026-08-07/municipios_PR.json").exists()
