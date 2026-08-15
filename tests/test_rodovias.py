import pytest

from ice_sul.extract.rodovias import load_catalog
from ice_sul.transform.rodovias import canonical_road_id, process, valid_geometry


def feature(road, uf, jurisdiction="estadual", pavement="Pavimentada", status="Existente", coordinates=None, **extra):
    return {"type": "Feature", "properties": {"rodovia": road, "uf": uf, "jurisdicao": jurisdiction, "pavimento": pavement, "situacao": status, **extra}, "geometry": {"type": "LineString", "coordinates": coordinates or [[-51, -25], [-50.9, -25]]}}


def source(source_id="der_pr", jurisdiction="estadual", uf="PR"):
    return {"source_id": source_id, "institution": source_id, "jurisdiction": jurisdiction, "uf": uf, "reference_date": "2026-08-12"}


def test_catalogo_cobre_fontes_oficiais_e_tres_ufs():
    catalog = load_catalog(__import__("pathlib").Path("data/raw/rodovias/catalogo-fontes.json"))
    assert {item.source_id for item in catalog} == {"dnit_snv", "der_pr", "geosie_sc", "daer_rs"}
    assert {uf for item in catalog for uf in item.states} == {"PR", "SC", "RS"}


@pytest.mark.parametrize(("raw", "uf", "expected"), [("BR 116", "PR", "BR-116"), ("PR-323", "PR", "PR-323"), ("401", "SC", "SC-401"), ("ERS-040", "RS", "RS-040")])
def test_identificacao_rodoviaria_harmonizada(raw, uf, expected):
    assert canonical_road_id(raw, uf) == expected


def test_elegibilidade_conservadora_inclui_concessao_e_exclui_ambiguos():
    records = [
        feature("PR-323", "PR", concessionaria="Concessionaria X"),
        feature("SC-401", "SC", pavement="Leito natural"),
        feature("RS-040", "RS", status="Planejada"),
        feature("PR-090", "PR", jurisdiction="municipal"),
        feature("BR-116", "PR", jurisdiction="federal", pavement=None),
    ]
    eligible, report = process([(source(), records)])
    assert [row["properties"]["rodovia_id"] for row in eligible] == ["PR-323"]
    assert eligible[0]["properties"]["concessao"] is True
    assert report["missing_pavimento"] == 1
    assert report["segmentos_elegiveis"] == 1


def test_qa_por_uf_jurisdicao_duplicidade_e_geometria_invalida():
    good = feature("BR-101", "SC", jurisdiction="federal")
    invalid = feature("SC-999", "SC", coordinates=[[999, -25], [-50, -25]])
    eligible, report = process([(source("dnit", "federal", "SC"), [good, good]), (source("sie", "estadual", "SC"), [invalid])])
    assert len(eligible) == 2 and report["duplicidades"] == 1
    assert report["geometrias_invalidas"] == 1
    assert report["cobertura"]["SC"]["federal"]["km"] > 0
    assert not valid_geometry(invalid["geometry"])
