import csv
import json
import zipfile

import pytest

from ice_sul.extract.cnpj import list_official_files
from ice_sul.transform.cnpj import ACTIVE_STATUS, build_numerators


def _zip(path, rows):
    import io
    data = io.StringIO(newline="")
    csv.writer(data, delimiter=";", lineterminator="\n").writerows(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fixture.csv", data.getvalue().encode("latin-1"))


def _est(root, order, status, uf, municipality):
    row = [""] * 30
    row[0:3] = [root, order, "01"]
    row[5], row[19], row[20] = status, uf, municipality
    return row


def test_official_index_discovers_all_parts(monkeypatch):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return (b'<a href="Estabelecimentos0.zip">e</a>'
                    b'<a href="Estabelecimentos1.zip">e</a>'
                    b'<a href="Simples.zip">s</a><a href="Municipios.zip">m</a>')
    monkeypatch.setattr("ice_sul.extract.cnpj.urlopen", lambda *a, **k: Response())
    urls = list_official_files("2026-07")
    assert len(urls) == 4
    assert urls[0].endswith("Estabelecimentos0.zip")


def test_active_establishments_and_official_mei_flag(tmp_path):
    canonical = tmp_path / "canonical.csv"
    canonical.write_text("municipio_id,municipio_nome,uf_sigla\n4106902,Curitiba,PR\n4205407,Florianópolis,SC\n", encoding="utf-8")
    municipalities = tmp_path / "Municipios.zip"
    simples = tmp_path / "Simples.zip"
    establishments = tmp_path / "Estabelecimentos0.zip"
    _zip(municipalities, [["7535", "CURITIBA"], ["8105", "FLORIANOPOLIS"]])
    # raiz, opção Simples e datas, opção MEI e datas
    _zip(simples, [["11111111", "S", "", "", "S", ""],
                   ["22222222", "S", "", "", "N", ""]])
    _zip(establishments, [
        _est("11111111", "0001", ACTIVE_STATUS, "PR", "7535"),
        _est("11111111", "0002", ACTIVE_STATUS, "PR", "7535"),  # duas unidades da mesma raiz
        _est("22222222", "0001", ACTIVE_STATUS, "SC", "8105"),
        _est("33333333", "0001", "08", "PR", "7535"),  # baixada
        _est("22222222", "0001", ACTIVE_STATUS, "SC", "8105"),  # duplicada
        _est("44444444", "0001", ACTIVE_STATUS, "SP", "7107"),
    ])
    output, report = tmp_path / "out.csv", tmp_path / "quality.json"
    quality = build_numerators(establishments=[establishments], simples_zip=simples,
        municipios_zip=municipalities, canonical_csv=canonical, output_csv=output,
        report_json=report, snapshot="2026-07")
    rows = {r["municipio_id"]: r for r in csv.DictReader(output.open())}
    assert rows["4106902"] == {"municipio_id": "4106902", "estabelecimentos_ativos_com_mei": "2",
        "estabelecimentos_ativos_sem_mei": "0", "estabelecimentos_ativos_mei": "2"}
    assert rows["4205407"]["estabelecimentos_ativos_sem_mei"] == "1"
    assert quality["duplicados_cnpj_descartados"] == 1
    assert quality["estabelecimentos_ativos_sul"] == 3
    assert json.loads(report.read_text())["situacao_ativa_codigo"] == "02"


def test_unmapped_active_municipality_fails_with_evidence(tmp_path):
    canonical = tmp_path / "canonical.csv"
    canonical.write_text("municipio_id,municipio_nome,uf_sigla\n4106902,Curitiba,PR\n", encoding="utf-8")
    for name, rows in (("Municipios.zip", [["9999", "OUTRA"]]), ("Simples.zip", []),
                       ("Estabelecimentos.zip", [_est("11111111", "0001", "02", "PR", "9999")])):
        _zip(tmp_path / name, rows)
    report = tmp_path / "quality.json"
    with pytest.raises(ValueError, match="não mapeado"):
        build_numerators(establishments=[tmp_path / "Estabelecimentos.zip"], simples_zip=tmp_path / "Simples.zip",
          municipios_zip=tmp_path / "Municipios.zip", canonical_csv=canonical, output_csv=tmp_path / "out.csv",
          report_json=report, snapshot="2026-07")
    assert json.loads(report.read_text())["status"] == "reprovado"
