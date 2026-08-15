import csv
from pathlib import Path

import py7zr
import pytest

from ice_sul.extract.contracts import CollectionStatus
from ice_sul.extract.rais import RaisArchive, RaisCollector
from ice_sul.extract.registry import build_collectors
from ice_sul.transform.rais import (
    extracted_comt,
    load_municipality_map,
    read_comt,
    resolve_columns,
    transform_archive,
)

FIXTURES = Path("tests/fixtures/rais")
MAP = {
    "410690": "4106902", "420540": "4205407", "430510": "4305108",
    "530010": "5300108",
}


def archive_fixture(tmp_path, fixture="RAIS_VINC_PUB_SUL_2024.comt"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    archive = tmp_path / "RAIS_VINC_PUB_TEST.7z"
    with py7zr.SevenZipFile(archive, "w") as seven:
        seven.write(FIXTURES / fixture, arcname=fixture)
    return archive


def test_official_2024_vinc_pub_headers_from_de_para_are_primary():
    reader, stream, metadata = read_comt(FIXTURES / "RAIS_VINC_PUB_SUL_2024.comt")
    try:
        columns = resolve_columns(reader.fieldnames)
    finally:
        stream.close()
    assert columns == {
        "municipio": "municípiotrabcódigo",
        "cnae": "cnae20classecódigo",
        "natureza": "naturezajurídicacódigo",
        "ativo": "indvínculoativo3112código",
    }
    assert metadata == {"encoding": "utf-8-sig", "delimitador": ";"}


def test_end_to_end_7z_comt_real_headers_filters_and_contract(tmp_path):
    archive = archive_fixture(tmp_path)
    with extracted_comt(archive) as member:
        assert member.suffix == ".comt"
    result = transform_archive(
        archive, file_uf="PR", municipality_map=MAP, year=2024,
        south_municipalities=["4106902", "4120002"],
    )
    assert result.private_employment == [{
        "municipio_id": "4106902", "empregos_formais_privados": 3,
        "periodo_referencia": "2024",
        "fonte": "MTE/PDET RAIS 2024 VINC_PUB; RAIS_VINC_PUB_TEST.7z",
    }]
    values = {row["municipio_id"]: row for row in result.diversification}
    assert values["4106902"]["valor_bruto"] == pytest.approx(4 / 9)
    assert values["4106902"]["flag_qualidade"] == "observado"
    assert values["4120002"]["valor_bruto"] is None
    assert values["4120002"]["flag_qualidade"] == "ausente_sem_vinculo_privado"
    assert list(values["4106902"]) == [
        "municipio_id", "indicador_id", "valor_bruto", "periodo_referencia", "flag_qualidade"
    ]
    assert result.quality["vinculos_lidos"] == 6
    assert result.quality["vinculos_inativos_excluidos"] == 1
    assert result.quality["vinculos_administracao_publica_excluidos"] == 2
    assert result.quality["vinculos_privados_elegiveis"] == 3
    assert result.quality["reconciliacao_ok"] is True


def test_brasilia_file_metadata_replaces_nonexistent_uf_column(tmp_path):
    result = transform_archive(
        archive_fixture(tmp_path, "RAIS_VINC_PUB_DF_2024.comt"),
        file_uf="DF", municipality_map=MAP,
        south_municipalities=[],
    )
    assert result.private_employment[0]["municipio_id"] == "5300108"
    assert result.quality["vinculos_lidos"] == 3
    assert result.quality["vinculos_inativos_excluidos"] == 1
    assert result.quality["vinculos_administracao_publica_excluidos"] == 1


def test_single_division_is_zero_and_unmatched_is_recorded(tmp_path):
    result = transform_archive(
        archive_fixture(tmp_path, "RAIS_VINC_PUB_DF_2024.comt"),
        file_uf="DF", municipality_map=MAP,
        south_municipalities=["5300108"],
    )
    assert result.diversification[0]["valor_bruto"] == 0
    limited = {key: value for key, value in MAP.items() if key != "530010"}
    unmatched = transform_archive(
        archive_fixture(tmp_path / "other", "RAIS_VINC_PUB_DF_2024.comt"),
        file_uf="DF", municipality_map=limited,
    )
    assert unmatched.quality["codigos_nao_ligados"] == {"530010": 2}


def test_explicit_municipality_crosswalk_uses_canonical_reference(tmp_path):
    reference = tmp_path / "municipios.csv"
    reference.write_text("municipio_id\n4106902\n5300108\n", encoding="utf-8")
    assert load_municipality_map(reference) == {
        "410690": "4106902", "4106902": "4106902",
        "530010": "5300108", "5300108": "5300108",
    }


def test_archive_rejects_missing_or_multiple_comt(tmp_path):
    archive = tmp_path / "bad.7z"
    text = tmp_path / "x.txt"; text.write_text("x")
    with py7zr.SevenZipFile(archive, "w") as seven: seven.write(text, "x.txt")
    with pytest.raises(ValueError, match="exatamente um"):
        with extracted_comt(archive): pass


def test_rais_collector_is_registered_and_reports_blocked_source(tmp_path, monkeypatch):
    assert build_collectors(["rais"])[0].source == "rais"
    reference = tmp_path / "south.csv"; reference.write_text("municipio_id\n4106902\n", encoding="utf-8")
    def blocked(*args, **kwargs):
        from urllib.error import HTTPError
        raise HTTPError("url", 503, "unavailable", {}, None)
    monkeypatch.setattr("ice_sul.extract.rais.download", blocked)
    result = RaisCollector(
        destination=tmp_path / "raw", interim=tmp_path / "interim",
        quality=tmp_path / "quality", south_reference=reference,
        archives=[RaisArchive("PR", "https://example.invalid/file.7z")],
    ).collect()
    assert result.status == CollectionStatus.BLOCKED_SOURCE
    assert result.errors
