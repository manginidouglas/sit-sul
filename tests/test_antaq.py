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


def test_reads_real_antaq_movement_evidence():
    from ice_sul.transform.antaq import read_antaq_movements
    rows = read_antaq_movements(Path("data/raw/antaq/anuario-2025-evidencias.tsv"))
    assert rows[0]["instalacao_id"] == "BRPNG"
    assert rows[0]["movimentacao_evidenciada_t"] == "19700000.0"
    assert rows[0]["pagina_ou_referencia"] == "p. 19"


def annual_installations():
    return [
        {"instalacao_id": "P", "nome": "Porto", "tipo": "Porto Organizado", "uf": "PR", "municipio": "X", "latitude": "-25", "longitude": "-48", "fonte_cadastro": "ANTAQ"},
        {"instalacao_id": "P0", "nome": "Porto sem prova", "tipo": "Porto Organizado", "uf": "SC", "municipio": "Y", "latitude": "-26", "longitude": "-49", "fonte_cadastro": "ANTAQ"},
        {"instalacao_id": "TG", "nome": "TUP geral", "tipo": "Terminal de uso privado", "uf": "", "municipio": "", "latitude": "-3", "longitude": "-60", "fonte_cadastro": "ANTAQ"},
        {"instalacao_id": "TB", "nome": "TUP bulk", "tipo": "Terminal de uso privado", "uf": "", "municipio": "", "latitude": "-4", "longitude": "-61", "fonte_cadastro": "ANTAQ"},
        {"instalacao_id": "TU", "nome": "TUP sem prova", "tipo": "Terminal de uso privado", "uf": "", "municipio": "", "latitude": "", "longitude": "", "fonte_cadastro": "ANTAQ"},
        {"instalacao_id": "IP", "nome": "IP4", "tipo": "IP4", "uf": "", "municipio": "", "latitude": "-5", "longitude": "-62", "fonte_cadastro": "ANTAQ"},
    ]


def annual_evidence(identifier, nature, evidence_type="movimentação positiva"):
    return {"instalacao_id": identifier, "movimentacao_evidenciada_t": "0.1", "natureza_carga_evidenciada": nature, "tipo_evidencia": evidence_type, "escopo_movimentacao_evidenciada": "parcial", "fonte_movimentacao": "ANTAQ", "pagina_ou_referencia": "p. 1", "periodo_inicio": "2025-01-01", "periodo_fim": "2025-12-31"}


def test_annual_statuses_do_not_require_months():
    from ice_sul.transform.antaq import evaluate_annual_installations
    proofs = [annual_evidence("P", "granel"), annual_evidence("TG", "carga geral"), annual_evidence("TB", "granel", "movimentação exclusivamente graneleira")]
    rows = {row["instalacao_uid"]: row for row in evaluate_annual_installations(annual_installations(), proofs)}
    assert rows["P"]["status_mvp"] == "elegivel"
    assert rows["P0"]["status_mvp"] == "indeterminado"
    assert rows["TG"]["status_mvp"] == "elegivel"
    assert rows["TB"]["status_mvp"] == "nao_elegivel"
    assert rows["TU"]["status_mvp"] == "indeterminado"
    assert rows["IP"]["status_mvp"] == "fora_escopo_mvp"
    assert rows["P"]["periodo_inicio"] == "2025-01-01"
    assert "periodo" not in rows["P"]


def test_real_annual_evidence_is_partial_not_total():
    from ice_sul.transform.antaq import read_antaq_movements
    row = read_antaq_movements(Path("data/raw/antaq/anuario-2025-evidencias.tsv"))[0]
    assert row["escopo_movimentacao_evidenciada"] == "milho e soja"
    assert "periodo" not in row


def test_resource_validators_reject_html_invalid_zip_and_pdf(tmp_path):
    from ice_sul.extract.antaq import validate_installations_zip, validate_yearbook_pdf
    html = tmp_path / "error.zip"; html.write_text("<html>erro</html>")
    with pytest.raises(ValueError, match="magic bytes ZIP"): validate_installations_zip(html)
    import zipfile
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as archive: archive.writestr("other.txt", "x")
    with pytest.raises(ValueError, match="Portos.xlsx"): validate_installations_zip(empty)
    pdf = tmp_path / "bad.pdf"; pdf.write_bytes(b"%PDF-bad")
    with pytest.raises(ValueError, match="truncado"): validate_yearbook_pdf(pdf)


def test_collector_never_succeeds_for_html(monkeypatch, tmp_path):
    def fake(url, destination, **kwargs):
        destination.write_text("<html>erro</html>")
        return {"url": url}
    monkeypatch.setattr("ice_sul.extract.antaq.download", fake)
    result = AntaqCollector(installations_path=tmp_path / "x.zip", yearbook_path=tmp_path / "x.pdf").collect()
    assert result.status == CollectionStatus.FAILED_VALIDATION


def test_registry_discovers_antaq_in_clean_subprocess():
    import subprocess, sys
    command = "from ice_sul.extract.registry import build_collectors; print(build_collectors(['antaq'])[0].source)"
    result = subprocess.run([sys.executable, "-c", command], check=True, text=True, capture_output=True)
    assert result.stdout.strip() == "antaq"


def test_collector_success_requires_validated_zip_and_pdf(monkeypatch, tmp_path):
    import zipfile
    def fake(url, destination, **kwargs):
        if destination.suffix == ".zip":
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("snapshot/Portos.xlsx", b"xlsx")
                archive.writestr("snapshot/Portos.dbf", b"dbf")
        else:
            destination.write_bytes(b"%PDF-1.7\n" + b"x" * 100_000 + b"\n%%EOF")
        return {"url": url}
    monkeypatch.setattr("ice_sul.extract.antaq.download", fake)
    result = AntaqCollector(installations_path=tmp_path / "x.zip", yearbook_path=tmp_path / "x.pdf").collect()
    assert result.status == CollectionStatus.SUCCESS
    assert all(entry["validacao"] == "formato e conteúdo estrutural validados" for entry in result.manifest_entries)




def _fixture_installations_zip(path, rows):
    import io, struct, zipfile
    fields = [("cdi_tuaria", 20), ("nome", 80), ("tipo", 40), ("estado", 2), ("cidade", 40), ("latitude", 20), ("longitude", 20), ("fonte", 20)]
    header_len, record_len = 32 + 32 * len(fields) + 1, 1 + sum(width for _, width in fields)
    header = bytearray(32); header[0] = 3; header[4:8] = len(rows).to_bytes(4, "little"); header[8:10] = header_len.to_bytes(2, "little"); header[10:12] = record_len.to_bytes(2, "little")
    descriptors = bytearray()
    for name, width in fields:
        descriptor = bytearray(32); descriptor[:len(name)] = name.encode(); descriptor[11] = ord("C"); descriptor[16] = width; descriptors += descriptor
    dbf = bytes(header + descriptors + b"\r")
    for row in rows:
        dbf += b" " + b"".join(str(row.get(name, "")).encode("cp1252").ljust(width) for name, width in fields)
    dbf += b"\x1a"
    headers = [name for name, _ in fields]
    shared = '<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + ''.join(f'<si><t>{value}</t></si>' for value in headers) + '</sst>'
    cells = ''.join(f'<c r="{chr(65+i)}1" t="s"><v>{i}</v></c>' for i in range(len(headers)))
    sheet = f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">{cells}</row>' + ''.join(f'<row r="{i+2}"/>' for i in range(len(rows))) + '</sheetData></worksheet>'
    xlsx = io.BytesIO()
    with zipfile.ZipFile(xlsx, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared); archive.writestr("xl/worksheets/sheet1.xml", sheet)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("snapshot/Portos.xlsx", xlsx.getvalue()); archive.writestr("snapshot/Portos.dbf", dbf)


def test_registry_fixture_preserves_accents(tmp_path):
    from ice_sul.transform.antaq import read_antaq_installations
    raw = tmp_path / "install.zip"
    _fixture_installations_zip(raw, [{"cdi_tuaria":"BRITJ", "nome":"Itajaí", "tipo":"Porto Organizado", "estado":"SC", "cidade":"Itajaí", "latitude":"-26", "longitude":"-48", "fonte":"ANTAQ"}])
    row = read_antaq_installations(raw)[0]
    assert row["nome"] == row["municipio"] == "Itajaí"
    assert "�" not in str(row)


def test_materialization_end_to_end_without_official_binaries(tmp_path, monkeypatch):
    import csv, hashlib, json
    import ice_sul.transform.antaq_materialize as module
    raw, interim, report = tmp_path/"raw", tmp_path/"interim", tmp_path/"report"
    raw.mkdir(); report.mkdir()
    zip_path = raw/"instalacoes-portuarias-2025-05-06.zip"
    _fixture_installations_zip(zip_path, [{"cdi_tuaria":"P", "nome":"Porto", "tipo":"Porto Organizado", "estado":"SC", "cidade":"X", "latitude":"-26", "longitude":"-48", "fonte":"ANTAQ"}])
    pdf = raw/"yearbook.pdf"; pdf.write_bytes(b"%PDF-1.7\n" + b"x"*100000 + b"\n%%EOF")
    evidence = raw/"anuario-2025-evidencias.tsv"
    evidence.write_text("instalacao_id\tnome_publicado\tvalor_publicado\tunidade\tescopo_movimentacao_evidenciada\tnatureza_carga_evidenciada\ttipo_evidencia\tfonte_movimentacao\turl\tpagina_ou_referencia\tperiodo_inicio\tperiodo_fim\tcoletado_em\nP\tPorto\t1\tt\tmovimentação total\tcarga geral\tmovimentação positiva\tANTAQ\thttps://oficial\tp.1\t2025-01-01\t2025-12-31\t2026-08-13\n", encoding="utf-8")
    manifest = report/"manifest.json"
    artifacts=[]
    for path in (zip_path,pdf): artifacts.append({"arquivo":str(path.relative_to(tmp_path)),"tamanho":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest.write_text(json.dumps({"artefatos":artifacts}))
    monkeypatch.setattr(module,"ROOT",tmp_path); monkeypatch.setattr(module,"RAW",raw); monkeypatch.setattr(module,"INTERIM",interim); monkeypatch.setattr(module,"REPORT",report); monkeypatch.setattr(module,"MANIFEST",manifest); monkeypatch.setattr(module,"UNIVERSE",interim/"universe.csv"); monkeypatch.setattr(module,"ELIGIBLE",interim/"eligible.csv"); monkeypatch.setattr(module,"QA",report/"qa.json"); monkeypatch.setattr(module,"MANUAL_IDS",["P"])
    monkeypatch.setattr(module,"read_antaq_movements",lambda _: __import__("ice_sul.transform.antaq",fromlist=["read_antaq_movements"]).read_antaq_movements(evidence))
    qa=module.materialize()
    assert qa["universo_cadastral"]["total"] == 1
    assert len(list(csv.DictReader(module.ELIGIBLE.open()))) == 1
