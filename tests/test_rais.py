import csv
import pytest

from ice_sul.transform.rais import (
    cnae_division,
    is_public_administration,
    resolve_columns,
    transform_rows,
    write_outputs,
)


COLUMNS = {
    "ano": "Ano",
    "municipio": "Município",
    "uf": "UF",
    "cnae": "CNAE 2.0 Classe",
    "natureza": "Natureza Jurídica",
    "ativo": "Vínculo Ativo 31/12",
}


def row(municipio, uf, cnae, natureza="2062", ativo="1", ano="2024"):
    return {
        "Ano": ano,
        "Município": municipio,
        "UF": uf,
        "CNAE 2.0 Classe": cnae,
        "Natureza Jurídica": natureza,
        "Vínculo Ativo 31/12": ativo,
    }


def test_resolves_realistic_rais_headers_and_requires_stock_concept():
    assert resolve_columns(COLUMNS.values()) == COLUMNS
    with pytest.raises(ValueError, match="ativo em 31/12"):
        resolve_columns(["Município", "UF", "CNAE", "Natureza Jurídica"])


def test_private_stock_and_diversification_exclude_public_by_both_rules(tmp_path):
    rows = [
        row("4106902", "PR", "1011201"),
        row("4106902", "PR", "4711301"),
        row("4106902", "PR", "4711301"),
        row("4106902", "PR", "8411600", natureza="3999"),  # divisão 84
        row("4106902", "PR", "8610101", natureza="1015"),  # natureza pública
        row("4205407", "SC", "4711301", ativo="0"),
        row("4305108", "RS", "6201501"),
    ]
    result = transform_rows(
        rows,
        columns=COLUMNS,
        year=2024,
        south_municipalities=["4106902", "4205407", "4305108"],
    )
    assert result.private_employment == [
        {"municipio_id": "4106902", "ano": 2024, "empregos_formais_privados": 3},
        {"municipio_id": "4305108", "ano": 2024, "empregos_formais_privados": 1},
    ]
    values = {item["municipio_id"]: item["valor"] for item in result.diversification}
    assert values["4106902"] == pytest.approx(1 - (1 / 3) ** 2 - (2 / 3) ** 2)
    assert values["4205407"] is None
    assert values["4305108"] == 0
    assert result.quality["empregos_publicos_excluidos"] == 2
    assert result.quality["vinculos_nao_ativos_descartados"] == 1

    write_outputs(result, tmp_path / "interim", tmp_path / "quality")
    with (tmp_path / "interim/mer_diag_01.csv").open() as stream:
        saved = list(csv.DictReader(stream))
    assert saved[1]["valor"] == ""


def test_aggregated_stock_is_supported_without_confusing_rows_and_jobs():
    columns = {**COLUMNS, "empregos": "Empregos"}
    columns.pop("ativo")
    item = row("3550308", "SP", "6201501")
    item["Empregos"] = "12"
    result = transform_rows([item], columns=columns, year=2024)
    assert result.private_employment[0]["empregos_formais_privados"] == 12


@pytest.mark.parametrize("value", ["", "0", "AA", "0010000"])
def test_rejects_invalid_cnae_division(value):
    with pytest.raises(ValueError):
        cnae_division(value)


def test_rejects_year_municipality_uf_and_negative_stock():
    with pytest.raises(ValueError, match="ano diferente"):
        transform_rows([row("4106902", "PR", "4711301", ano="2023")], columns=COLUMNS, year=2024)
    with pytest.raises(ValueError, match="não harmonizado"):
        transform_rows([row("410690", "PR", "4711301")], columns=COLUMNS, year=2024)
    with pytest.raises(ValueError, match="UF inconsistente"):
        transform_rows([row("4106902", "SC", "4711301")], columns=COLUMNS, year=2024)
    columns = {**COLUMNS, "empregos": "Empregos"}; columns.pop("ativo")
    bad = row("4106902", "PR", "4711301"); bad["Empregos"] = "-1"
    with pytest.raises(ValueError, match="impossível"):
        transform_rows([bad], columns=columns, year=2024)


def test_public_filter_is_reproducible():
    assert is_public_administration("8411600", "2062")
    assert is_public_administration("6201501", "1015")
    assert not is_public_administration("6201501", "2062")


def test_brasilia_high_public_administration_case_is_removed():
    result = transform_rows(
        [
            row("5300108", "DF", "8411600", natureza="1015"),
            row("5300108", "DF", "6201501", natureza="2062"),
        ],
        columns=COLUMNS,
        year=2024,
    )
    assert result.private_employment == [
        {"municipio_id": "5300108", "ano": 2024, "empregos_formais_privados": 1}
    ]
    assert result.quality["empregos_publicos_excluidos"] == 1


def test_rejects_duplicate_or_incomplete_south_universe():
    with pytest.raises(ValueError, match="duplicados"):
        transform_rows([], columns=COLUMNS, year=2024, south_municipalities=["4106902"] * 2)
    with pytest.raises(ValueError, match="cobertura"):
        transform_rows(
            [],
            columns=COLUMNS,
            year=2024,
            south_municipalities=["4106902"],
            expected_south_count=1191,
        )
