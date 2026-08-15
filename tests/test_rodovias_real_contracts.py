import json
import zipfile
from pathlib import Path

import pytest
import shapefile
from pyproj import CRS, Transformer
from email.message import Message
from urllib.error import HTTPError
from ice_sul.routing import Coordinate, MatrixResult

from ice_sul.extract.rodovias import validate_zip
from ice_sul.transform.rodovias import apply_precedence, canonical_road_id, concession_value, normalize_feature
from ice_sul.transform.rodovias_materialize import (
    _fetch, _fetch_alternatives, osrm_sensitivity_study, osrm_study, parse_daer_capabilities, parse_daer_gml,
    main, publish_generation, read_daer_geojson, read_der_zip, read_geosie, route_candidates, validate_daer_schema, validate_municipal_sample,
)


def geom(): return {"type": "LineString", "coordinates": [[-51.0, -30.0], [-50.9, -30.0]]}


def test_zip_shapefile_crc_componentes_e_traversal(tmp_path):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        for suffix in ("shp", "shx", "dbf", "prj"): z.writestr(f"SNV_202607A.{suffix}", suffix)
    assert len(validate_zip(good.read_bytes())) == 4
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z: z.writestr("../escape.shp", "x")
    with pytest.raises(ValueError, match="inseguro"): validate_zip(bad.read_bytes(), shapefile=False)


def test_der_adapter_valida_campos_e_reprojeta_31982(tmp_path):
    shp, shx, dbf = __import__("io").BytesIO(), __import__("io").BytesIO(), __import__("io").BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf)
    for field in ("Trecho", "Rod_Txt", "Situacao", "Jurisdicao", "TipoJuris", "Concessao"): writer.field(field, "C")
    xy = Transformer.from_crs("OGC:CRS84", "EPSG:31982", always_xy=True).transform(-51, -25)
    writer.line([[[xy[0], xy[1]], [xy[0] + 100, xy[1] + 100]]]); writer.record("x", "323", "PAV", "Estadual", "EPR", "")
    writer.close(); archive = tmp_path / "der.zip"; layer = "SRE_2021_UTM_SIRGAS2000_22S_LN"
    with zipfile.ZipFile(archive, "w") as z:
        for suffix, stream in (("shp", shp), ("shx", shx), ("dbf", dbf)): z.writestr(f"{layer}.{suffix}", stream.getvalue())
        z.writestr(f"{layer}.prj", CRS.from_epsg(31982).to_wkt())
    features, metadata = read_der_zip(archive)
    assert metadata["crs"] == "EPSG:31982" and features[0]["geometry"]["coordinates"][0] == pytest.approx([-51, -25])


def test_geosie_adapter_campos_reais(tmp_path):
    path = tmp_path / "sc.geojson"; props = {key: "PAV" for key in ("SGRODOVIA", "CDTRECHO", "NUGEO", "SGSITUACAO", "DESITUACAO")}
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": props, "geometry": geom()}]}))
    features, metadata = read_geosie(path)
    assert len(features) == metadata["records"] == 1


def test_coletor_de_producao_respeita_alternativas_oficiais(monkeypatch, tmp_path):
    calls = []
    def fake(url, path, mime):
        calls.append(url)
        if url.endswith("principal"): raise OSError("bloqueado")
        return {"requested_url": url, "final_url": url, "redirects": [], "content_type": mime[0]}
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize._fetch", fake)
    result = _fetch_alternatives(("https://org/principal", "https://org/alternativa"), tmp_path / "raw", ("application/zip",))
    assert calls == ["https://org/principal", "https://org/alternativa"]
    assert result["failed_attempts"][0]["url"].endswith("principal")


def test_reuso_preserva_proveniencia_http_original(tmp_path):
    raw = tmp_path / "raw.zip"; raw.write_bytes(b"PKpayload")
    digest = __import__("hashlib").sha256(raw.read_bytes()).hexdigest()
    original = {"requested_url": "https://org/inicial", "final_url": "https://org/final", "redirects": [{"status": 302}],
        "collected_at": "2026-08-14T00:00:00Z", "http_status": 200, "content_type": "application/zip",
        "bytes": len(raw.read_bytes()), "sha256": digest, "path": str(raw)}
    raw.with_suffix(".zip.http.json").write_text(json.dumps(original))
    reused = _fetch("https://org/inicial", raw, ("application/zip",))
    for field, value in original.items(): assert reused[field] == value
    assert reused["status"] == "reused" and "reused_at" in reused


def test_daer_retomada_reusa_primeiro_raw_quando_segundo_falha(monkeypatch, tmp_path):
    class Response:
        status, url = 200, "https://daer/final"
        headers = Message(); headers.add_header("Content-Type", "text/xml")
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"<WFS_Capabilities/>"
    class Opener:
        def open(self, request, timeout):
            if request.full_url.endswith("schema"): raise HTTPError(request.full_url, 403, "forbidden", {}, None)
            return Response()
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.build_opener", lambda *a: Opener())
    cap, schema = tmp_path / "capabilities.xml", tmp_path / "schema.xsd"
    first = _fetch("https://daer/cap", cap, ("text/xml",))
    with pytest.raises(HTTPError): _fetch("https://daer/schema", schema, ("text/xml",))
    assert cap.with_suffix(".xml.http.json").exists()
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.build_opener", lambda *a: (_ for _ in ()).throw(AssertionError("rede não deve ser usada")))
    resumed = _fetch("https://daer/cap", cap, ("text/xml",))
    assert resumed["status"] == "reused" and resumed["requested_url"] == first["requested_url"]


def test_dnit_campos_reais_e_regressao_zero_elegiveis():
    feature = {"properties": {"sg_uf": "PR", "vl_br": "116", "vl_codigo": "116BPR0010",
        "ds_jurisdi": "Federal", "sg_legenda": "PAV", "ds_legenda": "Pavimentada",
        "ds_superfi": "PAV", "ds_obra": "", "ds_tipo_ad": "DNIT"}, "geometry": geom()}
    row = normalize_feature(feature, {"source_id": "dnit_snv", "jurisdiction": "federal", "reference_date": "2026-07"})
    assert row["properties"]["elegivel"] and row["properties"]["chave_oficial"] == "116BPR0010"
    feature["properties"]["ds_obra"] = "EOD"
    assert not normalize_feature(feature, {"source_id": "dnit_snv", "jurisdiction": "federal"})["properties"]["elegivel"]
    feature["properties"]["ds_obra"] = ""
    feature["properties"]["sg_legenda"] = "PLA"
    assert not normalize_feature(feature, {"source_id": "dnit_snv", "jurisdiction": "federal"})["properties"]["elegivel"]


CAP = b'''<WFS_Capabilities><Service><Fees>none</Fees><AccessConstraints>vedado o uso comercial</AccessConstraints></Service><FeatureTypeList><FeatureType><Name>rod_sre</Name></FeatureType></FeatureTypeList></WFS_Capabilities>'''
SCHEMA = ('''<schema xmlns="http://www.w3.org/2001/XMLSchema">''' + "".join(f'<element name="{x}" type="string"/>' for x in
    ["codigo_sre", "nome", "rede", "administracao", "situacao_fisica", "revestimento", "concessao", "federal_superposta", "municipalizacao", "tipo_tracado"]) + "</schema>").encode()
GML = b'''<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml" xmlns:d="urn:daer"><gml:featureMember><d:rod_sre><d:codigo_sre>040ERS</d:codigo_sre><d:nome>ERS-040</d:nome><d:administracao>ESTADUAL-DAER</d:administracao><d:situacao_fisica>PAVIMENTADA</d:situacao_fisica><d:revestimento>ASFALTO</d:revestimento><d:geom><gml:LineString srsName="EPSG:4674"><gml:posList srsDimension="2">-30 -51 -30.1 -50.9</gml:posList></gml:LineString></d:geom></d:rod_sre></gml:featureMember></gml:FeatureCollection>'''


def test_daer_capabilities_schema_gml_e_ordem_dos_eixos():
    assert parse_daer_capabilities(CAP) == {"type_name": "rod_sre", "fees": "none", "access_constraints": "vedado o uso comercial"}
    assert "codigo_sre" in validate_daer_schema(SCHEMA)
    feature = parse_daer_gml(GML)[0]
    assert feature["geometry"]["coordinates"][0] == [-51.0, -30.0]
    row = normalize_feature(feature, {"source_id": "daer_rs", "jurisdiction": "estadual", "uf": "RS"})
    assert row["properties"]["elegivel"]


def test_daer_iede_geojson_oficial_tem_schema_contagem_e_bounds(tmp_path):
    properties = {field: "" for field in ("codigo_sre", "nome", "rede", "administracao", "situacao_fisica",
        "revestimento", "concessao", "federal_superposta", "municipalizacao", "tipo_tracado")}
    feature = {"type": "Feature", "properties": properties, "geometry": geom()}
    path = tmp_path / "daer.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature] * 1683}))
    features, metadata = read_daer_geojson(path)
    assert len(features) == metadata["records"] == 1683
    assert metadata["service"] == "IEDE/DAER Rodovias_RS MapServer/0"


@pytest.mark.parametrize(("raw", "uf", "jur", "expected"), [("116", "PR", "federal", "BR-116"),
    ("BRS-290", "RS", "federal", "BR-290"), ("ERS-040", "RS", "estadual", "RS-040"), ("RSC-453", "RS", "estadual", "RS-453")])
def test_prefixos_rodoviarios_reais(raw, uf, jur, expected):
    assert canonical_road_id(raw, uf, jur) == expected


def test_concessao_triestado():
    assert concession_value(None) is None and concession_value("Nulo") is None and concession_value("Não") is False
    assert concession_value("Federal-Concessionada") is True
    assert concession_value("categoria futura") is None


def test_precedencia_preserva_pistas_da_mesma_fonte():
    rows = []
    for n in range(2):
        f = {"properties": {"sg_uf": "PR", "vl_br": "116", "vl_codigo": str(n), "ds_jurisdi": "Federal", "sg_legenda": "PAV", "ds_superfi": "PAV"}, "geometry": geom()}
        rows.append(normalize_feature(f, {"source_id": "dnit_snv", "jurisdiction": "federal"}))
    kept, removed = apply_precedence(rows)
    assert len(kept) == 2 and removed == []
    assert kept[0]["properties"]["segmento_id"] != kept[1]["properties"]["segmento_id"]


def complete_sources():
    result = []
    for uf, state_source in (("PR", "der_pr"), ("SC", "geosie_sc"), ("RS", "daer_rs")):
        federal = {"properties": {"sg_uf": uf, "vl_br": "116", "vl_codigo": f"f-{uf}", "ds_jurisdi": "federal", "sg_legenda": "PAV", "ds_superfi": "PAV"}, "geometry": geom()}
        if state_source == "der_pr": props = {"uf": uf, "Rod_Txt": "PR-040", "Trecho": "e-PR", "Jurisdicao": "estadual", "Situacao": "Pavimentada"}
        elif state_source == "geosie_sc": props = {"uf": uf, "SGRODOVIA": "SC-040", "NUGEO": "e-SC", "jurisdicao": "estadual", "SGSITUACAO": "PAV"}
        else: props = {"uf": uf, "nome": "ERS-040", "codigo_sre": "e-RS", "administracao": "ESTADUAL-DAER", "situacao_fisica": "PAVIMENTADA"}
        state = {"properties": props, "geometry": geom()}
        result.append(({"source_id": "dnit_snv", "jurisdiction": "federal", "uf": uf}, [federal]))
        result.append(({"source_id": state_source, "jurisdiction": "estadual", "uf": uf}, [state]))
    return result


def test_portao_exige_seis_celulas(tmp_path):
    with pytest.raises(ValueError, match="cobertura incompleta"):
        publish_generation(complete_sources()[:-1], tmp_path / "published")


@pytest.mark.parametrize("phase", ["after_generation_promote", "before_pointer_swap", "after_pointer_swap"])
def test_publicacao_transacional_ponteiro_nunca_fica_ausente(tmp_path, phase):
    destination = tmp_path / "published"
    publish_generation(complete_sources(), destination, generation_id="old")
    old = (destination / "active.json").read_text()
    def fail(current, _):
        if current == phase: raise RuntimeError("injetada")
    with pytest.raises(RuntimeError): publish_generation(complete_sources(), destination, generation_id=f"new-{phase}", failure_hook=fail)
    assert (destination / "active.json").exists()
    if phase != "after_pointer_swap": assert (destination / "active.json").read_text() == old


def routing_row():
    return {"properties": {"segmento_id": "seg-interior", "rodovia_id": "BR-116", "jurisdicao": "federal", "uf": "PR", "fonte_id": "dnit_snv"},
            "geometry": {"type": "LineString", "coordinates": [[-51.1, -25], [-50.9, -25]]}}


def sample_12():
    return json.loads(Path("reports/quality/mvp-demo-2026/rodovias/amostra-municipal-osrm.json").read_text())["municipalities"]


class ChunkClient:
    def table_chunks(self, sources, destinations, **_):
        split = 2
        for start, stop in ((0, split), (split, len(destinations))):
            count = stop - start
            durations = [1.0 if -51.1 < point.longitude < -50.9 else 30.0
                         for point in destinations[start:stop]]
            yield start, stop, MatrixResult([durations], [[1000.0] * count], [sources[0]], list(destinations[start:stop]), [12.0], [25.0] * count)


def test_densificacao_interior_vence_extremos_e_vinculo_sobrevive_chunks():
    candidates = route_candidates([routing_row()], max_spacing_m=8_000)
    assert len(candidates) >= 4 and -51.1 < candidates[1]["coordinate"].longitude < -50.9
    report = osrm_study([routing_row()], sample_12(), ChunkClient(), max_spacing_m=8_000)
    winner = report["municipalities"][0]["federal"]
    assert winner["segmento_id"] == "seg-interior" and -51.1 < winner["candidate"]["longitude"] < -50.9
    assert winner["origin_snap_meters"] == 12 and winner["destination_snap_meters"] == 25


def test_densificacao_aceita_aresta_menor_que_o_espacamento():
    short = routing_row(); short["geometry"]["coordinates"] = [[-51.0, -25.0], [-50.999, -25.0]]
    assert len(route_candidates([short], max_spacing_m=5_000)) == 2


class FailureClient:
    def table_chunks(self, sources, destinations, **_):
        count = len(destinations)
        yield 0, count, MatrixResult([[None] * count], [[None] * count], [sources[0]], list(destinations), [None], [None] * count)


def test_osrm_falha_e_snapping_sao_auditaveis():
    report = osrm_study([routing_row()], sample_12(), FailureClient())
    assert report["route_failures"] == 12
    assert report["municipalities"][0]["federal"]["route_failure"] is True


class ExcessiveSnapClient(ChunkClient):
    def table_chunks(self, sources, destinations, **kwargs):
        for start, stop, matrix in super().table_chunks(sources, destinations, **kwargs):
            matrix.source_snap_distances_meters[0] = 2_000
            yield start, stop, matrix


def test_decisao_bloqueada_por_snapping_excessivo():
    report = osrm_study([routing_row()], sample_12(), ExcessiveSnapClient(), max_spacing_m=8_000)
    assert report["methodological_decision"] == "exige_definicao_adicional_de_estruturante"
    assert report["snapping"]["excessive_winners_by_scenario"] == {"federal": 12, "federal_estadual": 12}


def test_sensibilidade_estavel_e_mudanca_entre_espacamentos(monkeypatch):
    def result(segment):
        scenario = {"route_failure": False, "segmento_id": segment, "duration_minutes": 2}
        return {"municipalities": [{"municipio_id": "x", "federal": scenario, "federal_estadual": scenario}], "n": 1,
                "snapping": {"excessive_winners_by_scenario": {"federal": 0, "federal_estadual": 0}},
                "methodological_decision": "exige_definicao_adicional_de_estruturante", "substantive_decision_without_snap_gate": "inclusao_melhora_marginalmente", "route_failures": 0}
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.osrm_study", lambda *a, max_spacing_m, **k: result("same"))
    stable = osrm_sensitivity_study([], [], object())
    assert stable["stable"] and stable["methodological_decision"] == "inclusao_melhora_marginalmente"
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.osrm_study", lambda *a, max_spacing_m, **k: result(str(max_spacing_m)))
    changed = osrm_sensitivity_study([], [], object())
    assert not changed["stable"] and changed["methodological_decision"] == "exige_definicao_adicional_de_estruturante"


def test_sensibilidade_estavel_nao_libera_snapping_excessivo(monkeypatch):
    scenario = {"route_failure": False, "segmento_id": "same", "duration_minutes": 2}
    result = {"municipalities": [{"municipio_id": "x", "federal": scenario, "federal_estadual": scenario}], "n": 1,
        "snapping": {"excessive_winners_by_scenario": {"federal": 1, "federal_estadual": 1}}, "route_failures": 0,
        "methodological_decision": "exige_definicao_adicional_de_estruturante", "substantive_decision_without_snap_gate": "inclusao_melhora_marginalmente"}
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.osrm_study", lambda *a, **k: result)
    report = osrm_sensitivity_study([], [], object())
    assert report["stable"] and not report["no_excessive_snap"]
    assert report["methodological_decision"] == "exige_definicao_adicional_de_estruturante"


def test_amostra_agregada_sem_as_doze_celulas_e_rejeitada():
    sample = sample_12()
    for item in sample:
        if item["uf"] in {"SC", "RS"}: item["estrato"] = "metropolitana"
    with pytest.raises(ValueError, match="12 células"): validate_municipal_sample(sample)


def test_amostra_rejeita_duplicidade_coordenada_e_id_fora_ibge():
    duplicated = sample_12(); duplicated[1]["municipio_id"] = duplicated[0]["municipio_id"]
    with pytest.raises(ValueError, match="duplicado"): validate_municipal_sample(duplicated)
    invalid = sample_12(); invalid[0]["latitude"] = 999
    with pytest.raises(ValueError, match="coordenada"): validate_municipal_sample(invalid)
    absent = sample_12(); absent[0]["municipio_id"] = "9999999"
    with pytest.raises(ValueError, match="ausente"): validate_municipal_sample(absent)
    mismatch = sample_12(); mismatch[0]["municipio_nome"] = "Curitiba"
    with pytest.raises(ValueError, match="nome/UF"): validate_municipal_sample(mismatch)
    swapped = sample_12(); swapped[0]["latitude"] = sample_12()[1]["latitude"]
    with pytest.raises(ValueError, match="diverge"): validate_municipal_sample(swapped)


def test_cli_completa_publica_e_imprime_resumo_sem_keyerror(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.collect_all", lambda *a: {key: {"status": "ok"} for key in ("dnit_snv", "der_pr", "geosie_sc", "daer_rs")})
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.load_collected", lambda *a: complete_sources())
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.mandatory_inspections", lambda rows: {"ok": len(rows)})
    study = {"n": 12, "route_failures": 0, "snapping_by_spacing_and_scenario": {}, "methodological_decision": "inclusao_melhora_marginalmente"}
    monkeypatch.setattr("ice_sul.transform.rodovias_materialize.osrm_sensitivity_study", lambda *a, **k: study)
    sample = tmp_path / "sample.json"; sample.write_text(json.dumps({"municipalities": sample_12()}))
    output, qa = tmp_path / "published", tmp_path / "qa"
    assert main(["--catalog", str(tmp_path / "catalog.json"), "--raw-root", str(tmp_path / "raw"),
                 "--output", str(output), "--qa-root", str(qa), "--municipal-sample", str(sample)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["study_n"] == 12 and (output / "active.json").exists()
