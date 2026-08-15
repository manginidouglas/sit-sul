import zipfile
from pathlib import Path

import py7zr
import pytest

from ice_sul.extract.contracts import CollectionStatus
from ice_sul.extract.rais import (
    OfficialRoutesUnavailable,
    RaisArchive,
    RaisCollector,
    download_large,
    archives_from_listing,
    reused_manifest,
    validate_7z,
    validate_xlsx,
)
from ice_sul.extract.registry import build_collectors
from ice_sul.transform.rais import (
    extracted_comt,
    load_municipality_map,
    read_comt,
    resolve_columns,
    transform_archive,
    transform_rows,
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
    assert values["4120002"]["flag_qualidade"] == "ausente"
    assert values["4120002"]["motivo_qualidade"] == "sem_vinculo_privado"
    assert list(values["4106902"]) == [
        "municipio_id", "indicador_id", "valor_bruto", "periodo_referencia",
        "flag_qualidade", "motivo_qualidade",
    ]
    assert result.quality["vinculos_lidos"] == 6
    assert result.quality["vinculos_ativos_lidos"] == 5
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
    assert result.diversification[0]["flag_qualidade"] == "zero_observado"
    limited = {key: value for key, value in MAP.items() if key != "530010"}
    unmatched = transform_archive(
        archive_fixture(tmp_path / "other", "RAIS_VINC_PUB_DF_2024.comt"),
        file_uf="DF", municipality_map=limited,
    )
    assert unmatched.quality["codigos_nao_ligados"] == {"530010": 2}
    assert unmatched.quality["vinculos_municipio_nao_ligado"] == 2
    assert unmatched.quality["reconciliacao_territorial_ok"] is True


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


def test_large_download_exhausts_https_and_ftp_before_blocking(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    monkeypatch.setattr(
        "ice_sul.extract.rais._download_https",
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPError("url", 503, "busy", {}, None)),
    )
    monkeypatch.setattr(
        "ice_sul.extract.rais._download_ftp",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("FTP blocked")),
    )
    with pytest.raises(OfficialRoutesUnavailable) as caught:
        download_large("https://ftp.mtps.gov.br/file.7z", tmp_path / "file.7z", uf="DF")
    attempts = caught.value.attempts
    assert [item["metodo"] for item in attempts] == ["GET", "FTP RETR"]
    assert attempts[0]["status_http"] == 503
    assert attempts[1]["url"].startswith("ftp://ftp.mtps.gov.br/")
    required = {
        "fonte", "url", "metodo", "parametros", "periodo", "data_hora_utc",
        "status_http", "resposta_ftp", "url_final", "redirects", "content_type",
        "tamanho_transferido", "tamanho_persistido", "sha256", "arquivo",
        "licenca", "versao_snapshot", "validacao",
    }
    assert required <= attempts[1].keys()


def test_archive_names_come_from_complete_official_listing():
    links = [f"RAIS_VINC_PUB_{uf}.7z" for uf in
             "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()]
    links += ["README.txt", "RAIS_ESTAB_PUB_PR.7z"]
    archives = archives_from_listing(links)
    assert len(archives) == 27
    assert archives[-1].filename == "RAIS_VINC_PUB_TO.7z"
    with pytest.raises(ValueError, match="UFs ausentes"):
        archives_from_listing(links[:-3])


def test_strict_domains_reject_unknown_active_and_legal_nature():
    columns = {"municipio": "m", "cnae": "c", "natureza": "n", "ativo": "a"}
    base = {"m": "410690", "c": "6201501", "n": "2062", "a": "2"}
    with pytest.raises(ValueError, match="ativo desconhecido"):
        transform_rows([base], columns=columns, year=2024, file_uf="PR", municipality_map=MAP)
    for invalid in ("", "9999", "206"):
        row = {**base, "a": "1", "n": invalid}
        with pytest.raises(ValueError, match="Natureza Jurídica"):
            transform_rows([row], columns=columns, year=2024, file_uf="PR", municipality_map=MAP)


def test_full_container_validation_and_reuse_manifest(tmp_path):
    archive = archive_fixture(tmp_path)
    assert "7-Zip íntegro" in validate_7z(archive)
    xlsx = tmp_path / "de-para.xlsx"
    with zipfile.ZipFile(xlsx, "w") as book:
        book.writestr("[Content_Types].xml", "<Types/>")
        book.writestr("xl/workbook.xml", "<workbook/>")
    assert validate_xlsx(xlsx) == "XLSX OOXML íntegro"
    entry = reused_manifest(xlsx, url="https://example.test/de-para.xlsx", uf="BR",
                            validation=validate_xlsx(xlsx))
    assert entry["metodo"] == "REUSE" and entry["reutilizado"] is True
    assert entry["tamanho_persistido"] == xlsx.stat().st_size
    assert len(entry["sha256"]) == 64
    broken = tmp_path / "broken.xlsx"; broken.write_bytes(b"PK not a workbook")
    with pytest.raises(ValueError, match="XLSX inválido"):
        validate_xlsx(broken)
