from datetime import date
from pathlib import Path
import io
import urllib.error
import pytest
from ice_sul.transform.anac import (build_airport_scores, coordinate, latest_complete_window,
    read_aerodromes, read_movements, write_airport_scores, unify_aerodromes, publish_atomic,
    read_siros, write_csv, assess_publication_integrity)
from ice_sul.extract.anac import download_resumable, sha256_stream, ValidationError, validate_aerodromes, AnacCollector
from ice_sul.extract.contracts import CollectionStatus

FIXTURES = Path(__file__).parent / "fixtures/anac"

def movement(year, month, *, origin="SBPA", destination="SBCT", group="REGULAR", departures="1", seats="100", paid="1", nature="DOMÉSTICA"):
    return {"ANO":str(year), "MES":str(month), "AEROPORTO_DE_ORIGEM_SIGLA":origin,
            "AEROPORTO_DE_DESTINO_SIGLA":destination, "NATUREZA":nature, "GRUPO_DE_VOO":group,
            "PASSAGEIROS_PAGOS":paid, "PASSAGEIROS_GRATIS":"0", "ASSENTOS":seats, "DECOLAGENS":departures}

def months(): return [(2025,m) for m in range(7,13)] + [(2026,m) for m in range(1,7)]

def test_real_headers_and_coordinate_formats():
    airports=read_aerodromes(FIXTURES/"aerodromos_reais.csv")
    assert airports[0]["aeroporto_id"] == "SBPA" and airports[0]["latitude"] == pytest.approx(-29.9938889)
    assert airports[1]["latitude"] == pytest.approx(-25.5317)
    version, rows=read_movements(FIXTURES/"movimentos_cabecalho_real.csv")
    assert version == "Atualizado em: 2026-08-09" and next(rows)["DECOLAGENS"] == "7"

def test_aggregated_departures_exactly_five_and_six_months_and_international():
    airports=read_aerodromes(FIXTURES/"aerodromos_reais.csv")
    baseline=[movement(y,m,origin="XXXX") for y,m in months()]
    active=[movement(y,m,departures="7", destination="SUMU" if i==0 else "SBCT", nature="INTERNACIONAL" if i==0 else "DOMÉSTICA") for i,(y,m) in enumerate(months()[:6])]
    rows,qa=build_airport_scores(airports,baseline+active)
    poa=next(r for r in rows if r["aeroporto_id"]=="SBPA")
    assert poa["meses_com_servico"] == 6 and poa["elegivel"] is True
    assert poa["decolagens"] == 42 and poa["destinos_distintos"] == 2
    five=baseline+active[:-1]
    assert next(r for r in build_airport_scores(airports,five)[0] if r["aeroporto_id"]=="SBPA")["elegivel"] is False
    # Sem país/UF no helper legado, uma origem não catalogada é diagnóstico externo.
    assert next(r for r in qa["origens_externas"] if r["codigo"] == "XXXX")["decolagens"] == 12

def test_zero_nonregular_and_cargo_do_not_count():
    airports=read_aerodromes(FIXTURES/"aerodromos_reais.csv")
    baseline=[movement(y,m,origin="XXXX") for y,m in months()]
    excluded=[movement(2026,6,departures="0"), movement(2026,6,group="NÃO REGULAR"), movement(2026,6,seats="0",paid="0")]
    row=next(r for r in build_airport_scores(airports,baseline+excluded)[0] if r["aeroporto_id"]=="SBPA")
    assert row["decolagens"] == 0 and not row["elegivel"]

def test_incomplete_window_and_schema_change(tmp_path):
    with pytest.raises(ValueError, match="janela incompleta"):
        latest_complete_window([movement(2026,m) for m in range(1,7)])
    bad=tmp_path/"bad.csv";bad.write_text("Atualizado em: x\nANO;MES\n",encoding="utf-8")
    with pytest.raises(ValueError, match="schema inesperado"): read_movements(bad)

def test_duplicate_missing_codes_bad_coordinates_and_empty_publish(tmp_path):
    airports=read_aerodromes(FIXTURES/"aerodromos_reais.csv")
    with pytest.raises(ValueError, match="duplicado"): build_airport_scores(airports+airports[:1],[movement(y,m) for y,m in months()])
    with pytest.raises(ValueError, match="identificador"): build_airport_scores([{"latitude":0,"longitude":0}],[])
    with pytest.raises(ValueError, match="fora da faixa"): coordinate("91",latitude=True)
    with pytest.raises(ValueError, match="vazio"): write_airport_scores([],tmp_path/"out.csv")

def test_sensitivity_multiple_airports_thresholds_and_decay():
    from ice_sul.transform.anac_sensitivity import compare_access_scenarios
    airports={"A":{"decolagens":100,"destinos_distintos":4,"score_exploratorio_frequencia_diversidade":20},
              "B":{"decolagens":25,"destinos_distintos":9,"score_exploratorio_frequencia_diversidade":15}}
    routes=[{"municipio_id":"1","aeroporto_id":"A","tempo_minutos":60},
            {"municipio_id":"1","aeroporto_id":"B","tempo_minutos":150}]
    rows=compare_access_scenarios(routes,airports)
    assert any(r["metrica"] == "score_exploratorio_frequencia_diversidade" for r in rows)
    score90=next(r for r in rows if r["limite_minutos"]==90 and r["metrica"]=="decolagens")
    score180=next(r for r in rows if r["limite_minutos"]==180 and r["metrica"]=="decolagens")
    assert score90["aeroportos_acessiveis"]==1 and score180["aeroportos_acessiveis"]==2
    assert score180["soma_sem_decaimento"]==125 and score180["soma_exponencial"] < 125


class Response(io.BytesIO):
    def __init__(self, payload, *, status=200, headers=None):
        super().__init__(payload); self.status=status; self.headers=headers or {"Content-Type":"text/csv","Content-Length":str(len(payload))}
    def getcode(self): return self.status
    def geturl(self): return "https://official.example/file.csv"


class FailingResponse(Response):
    def __init__(self, *, headers=None): super().__init__(b"",status=200,headers=headers);self.reads=0
    def read(self,*_args):
        self.reads+=1
        if self.reads==1:return b"OLD"
        raise ConnectionError("connection dropped")


def test_download_validates_before_atomic_promotion_and_reuses(tmp_path, monkeypatch):
    destination=tmp_path/"raw.csv"; payload=b"header\nvalue\n"
    seen=[]
    def validator(path): seen.append(path.suffix); assert not destination.exists(); return "v1"
    entry=download_resumable("https://official.example/file.csv",destination,validator=validator,minimum_size=5,opener=lambda *_a,**_k:Response(payload),sleeper=lambda _:None)
    assert entry["status"]=="downloaded" and seen==[".part"] and destination.read_bytes()==payload
    monkeypatch.setattr(Path,"read_bytes",lambda _p: (_ for _ in ()).throw(AssertionError("proibido")))
    assert download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v1",minimum_size=5)["status"]=="reused"
    assert sha256_stream(destination)==entry["sha256"]


@pytest.mark.parametrize("payload", [b"<html>blocked</html>", b"x"])
def test_invalid_received_bytes_never_promoted(tmp_path,payload):
    destination=tmp_path/"raw.csv"
    with pytest.raises(ValidationError):
        download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v1",minimum_size=5,opener=lambda *_a,**_k:Response(payload),sleeper=lambda _:None)
    assert not destination.exists() and not destination.with_suffix(".csv.part").exists()


def test_invalid_existing_raw_is_not_reused(tmp_path):
    destination=tmp_path/"raw.csv"; destination.write_text("bad")
    with pytest.raises(ValidationError,match="raw existente inválido"):
        download_resumable("https://official.example/file.csv",destination,validator=lambda _p:(_ for _ in ()).throw(ValueError("schema")),minimum_size=1)


def test_resume_content_range_and_server_ignoring_range(tmp_path):
    destination=tmp_path/"raw.csv"; partial=destination.with_suffix(".csv.part"); partial.write_bytes(b"abc")
    partial.with_suffix(".part.json").write_text('{"etag":"same"}')
    response=Response(b"def",status=206,headers={"Content-Type":"text/csv","Content-Range":"bytes 3-5/6","ETag":"same"})
    download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,opener=lambda *_a,**_k:response)
    assert destination.read_bytes()==b"abcdef"
    destination.unlink(); partial.write_bytes(b"old")
    download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,opener=lambda *_a,**_k:Response(b"new",status=200))
    assert destination.read_bytes()==b"new"


def test_same_call_failure_without_identity_never_concatenates_old_new(tmp_path):
    destination=tmp_path/"raw.csv";responses=[FailingResponse(headers={"Content-Type":"text/csv"}),Response(b"NEW",status=206,headers={"Content-Type":"text/csv","Content-Range":"bytes 3-5/6"})]
    requests=[]
    def opener(request,**_kwargs):requests.append(dict(request.header_items()));return responses.pop(0)
    with pytest.raises(ValidationError,match="206 inesperada"):
        download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,attempts=2,opener=opener,sleeper=lambda _:None)
    assert not destination.exists() and not destination.with_suffix(".csv.part").exists()
    assert not any("Range" in headers for headers in requests)


def test_same_call_failure_with_etag_requires_etag_on_followup(tmp_path):
    destination=tmp_path/"raw.csv";responses=[FailingResponse(headers={"Content-Type":"text/csv","ETag":"same"}),Response(b"NEW",status=206,headers={"Content-Type":"text/csv","Content-Range":"bytes 3-5/6"})]
    def opener(*_args,**_kwargs):return responses.pop(0)
    with pytest.raises(ValidationError,match="versão"):
        download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,attempts=2,opener=opener,sleeper=lambda _:None)
    assert not destination.exists()


@pytest.mark.parametrize("content_range,etag", [("bytes 2-4/5","same"),("bytes 3-5/6","different")])
def test_incompatible_resume_is_validation_failure(tmp_path,content_range,etag):
    destination=tmp_path/"raw.csv"; partial=destination.with_suffix(".csv.part"); partial.write_bytes(b"abc"); partial.with_suffix(".part.json").write_text('{"etag":"same"}')
    response=Response(b"def",status=206,headers={"Content-Type":"text/csv","Content-Range":content_range,"ETag":etag})
    with pytest.raises(ValidationError): download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,opener=lambda *_a,**_k:response)
    assert not partial.exists()


@pytest.mark.parametrize("code",[401,403,429,502,503,504])
def test_http_failures_are_preserved_for_classification(tmp_path,code):
    def fail(*_a,**_k): raise urllib.error.HTTPError("u",code,"failure",{},None)
    expected=urllib.error.HTTPError if code in (401,403) else RuntimeError
    with pytest.raises(expected): download_resumable("https://official.example/x",tmp_path/"x",opener=fail,attempts=2,sleeper=lambda _:None)


def _collector_with_manifest(tmp_path, payload=None):
    ids=("movimentos","publicos","privativos","helipontos","helidecks","siros")
    manifest=tmp_path/"frozen.json"
    manifest.write_text(__import__('json').dumps(payload if payload is not None else {"artefatos":[{"id":item,"sha256":"0"*64} for item in ids]}),encoding="utf-8")
    return AnacCollector(frozen_manifest_path=manifest)


def test_collector_success_has_no_unbound_error(tmp_path,monkeypatch):
    import ice_sul.extract.anac as module
    monkeypatch.setattr(module,"download_resumable",lambda url,path,**kwargs:{"arquivo":str(path),"sha256":kwargs["expected_sha256"]})
    result=_collector_with_manifest(tmp_path).collect()
    assert result.status==CollectionStatus.SUCCESS and len(result.manifest_entries)==6


@pytest.mark.parametrize(("payload","expected"),[
    ({},CollectionStatus.FAILED_VALIDATION),
    ({"artefatos":[]},CollectionStatus.FAILED_VALIDATION),
    ({"artefatos":[{"id":"movimentos","sha256":"0"*64}]},CollectionStatus.FAILED_VALIDATION),
])
def test_collector_rejects_invalid_or_incomplete_frozen_manifest(tmp_path,payload,expected):
    assert _collector_with_manifest(tmp_path,payload).collect().status==expected


def test_collector_rejects_malformed_json_and_missing_manifest(tmp_path):
    malformed=tmp_path/"bad.json";malformed.write_text("{")
    assert AnacCollector(frozen_manifest_path=malformed).collect().status==CollectionStatus.FAILED_VALIDATION
    assert AnacCollector(frozen_manifest_path=tmp_path/"missing.json").collect().status==CollectionStatus.FAILED_VALIDATION


@pytest.mark.parametrize(("error","expected"),[
    (ValidationError("hash divergente"),CollectionStatus.FAILED_VALIDATION),
    (urllib.error.HTTPError("u",401,"blocked",{},None),CollectionStatus.BLOCKED_SOURCE),
    (RuntimeError("429 após retries"),CollectionStatus.UNAVAILABLE),
    (TimeoutError("timeout"),CollectionStatus.BLOCKED_ENVIRONMENT),
    (PermissionError("denied"),CollectionStatus.BLOCKED_ENVIRONMENT),
    (OSError(__import__('errno').ENOSPC,"disk full"),CollectionStatus.BLOCKED_ENVIRONMENT),
])
def test_collector_failure_paths_are_classified_without_unbound_error(tmp_path,monkeypatch,error,expected):
    import ice_sul.extract.anac as module
    def fail(*_args,**_kwargs): raise error
    monkeypatch.setattr(module,"download_resumable",fail)
    result=_collector_with_manifest(tmp_path).collect()
    assert result.status==expected and result.errors and "UnboundLocalError" not in result.errors[0]


def test_public_private_union_alias_and_rotorcraft_exclusion(tmp_path):
    header="Aeródromo;;;;;;;;;;\nCÓDIGO OACI;CIAD;NOME;MUNICÍPIO ATENDIDO;UF;LATITUDE;LONGITUDE;TIPO DE INFRAESTRUTURA;SITUAÇÃO CADASTRAL;VALIDADE\n"
    public=tmp_path/"public.csv"; private=tmp_path/"private.csv"
    public.write_text(header+'SBPA;RS0001;POA;PORTO ALEGRE;RS;-29,9;-51,1;AERÓDROMO;ATIVO;\nSSHH;RS9999;H;X;RS;-29;-51;HELIPONTO;ATIVO;\n',encoding="utf-8")
    private.write_text(header+';BA0001;PRIVADO;CAIRU;BA;-13,3;-38,9;AERÓDROMO;ATIVO;\nSHDK;RJ0001;D;RIO;RJ;-22;-43;HELIDECK;ATIVO;\n',encoding="utf-8")
    rows,aliases=unify_aerodromes(read_aerodromes(public),read_aerodromes(private,tipo_cadastro="privativo"))
    assert len(rows)==2 and {r["tipo_cadastro"] for r in rows}=={"publico","privativo"} and aliases["BA0001"]=="BA0001"


def test_catalogue_collisions_and_invalid_domains():
    base={"aeroporto_id":"A","oaci":"A","ciad":"X","latitude":0,"longitude":0}
    with pytest.raises(ValueError,match="duplicado"): unify_aerodromes([base],[base])
    with pytest.raises(ValueError,match="ambíguo"): unify_aerodromes([base],[{**base,"aeroporto_id":"B","oaci":"B"}])


def test_brazilian_unlinked_blocks_coverage_and_reconciles():
    airport={"aeroporto_id":"SBPA","oaci":"SBPA","ciad":"RS1","latitude":-30,"longitude":-51,"tipo_cadastro":"publico","uf":"RS"}
    data=[]
    for y,m in months():
        row=movement(y,m,origin="MISS"); row.update(AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_ORIGEM_UF="BA",AEROPORTO_DE_ORIGEM_NOME="Ausente",AEROPORTO_DE_DESTINO_PAIS="BRASIL",AEROPORTO_DE_DESTINO_UF="RS",AEROPORTO_DE_DESTINO_NOME="POA"); data.append(row)
    _,qa=build_airport_scores([airport],data)
    assert not qa["coverage_complete"] and qa["origens_brasileiras_sem_cadastro"][0]["atingiria_limiar_se_ligada"]
    assert all(qa["reconciliacoes"].values())


def test_alias_destination_self_loop_and_private_exactly_six_months():
    airport={"aeroporto_id":"PRIV","oaci":"PRIV","ciad":"BA1","latitude":-13,"longitude":-39,"tipo_cadastro":"privativo","uf":"BA"}
    data=[]
    for y,m in months()[:6]:
        row=movement(y,m,origin="BA1",destination="PRIV"); row.update(AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_ORIGEM_UF="BA",AEROPORTO_DE_DESTINO_PAIS="BRASIL",AEROPORTO_DE_DESTINO_UF="BA"); data.append(row)
    rows,qa=build_airport_scores([airport],data)
    assert not rows[0]["elegivel"] and rows[0]["flag_qualidade"]=="indeterminado_servico_comercial"
    assert rows[0]["tipo_cadastro"]=="privativo" and rows[0]["destinos_distintos"]==0
    assert qa["destinos"]["self_loops_removidos"]==6 and rows[0]["metrica_status"]=="exploratoria_nao_congelada"


def test_atomic_publish_lf_and_failure_keeps_old_outputs(tmp_path):
    one=tmp_path/"one.csv"; two=tmp_path/"two.csv"; one.write_text("old\n"); two.write_text("old\n")
    publish_atomic({one:([{"a":1}], ["a"]),two:([{"b":2}], ["b"])})
    assert b"\r\n" not in one.read_bytes()
    old=one.read_bytes()
    with pytest.raises(Exception): publish_atomic({one:([{"a":3}],["a"]),two:object()})
    assert one.read_bytes()==old


def test_complete_official_fields_are_preserved_without_defaults(tmp_path):
    path=tmp_path/"private.csv"
    path.write_text("Atualizado em: 2026-08-17\nCódigo OACI;CIAD;Nome;Município;UF;Longitude;Latitude;LATGEOPOINT;LONGEOPOINT\nSDLO;BA0074;Fábio Perini;CAIRU;BA;038°56'20\"W;13°33'52\"S;-13,564444;-38,938889\n",encoding="utf-8")
    row=read_aerodromes(path,tipo_cadastro="privativo")[0]
    assert row["ciad"]=="BA0074" and row["situacao_cadastral"]=="" and row["validade"]==""
    assert row["tipo_infraestrutura"]=="AERODROMO" and row["versao_fonte"]=="Atualizado em: 2026-08-17"


def test_siros_full_acquisition_parser_and_ssou_evidence(tmp_path):
    path=tmp_path/"siros.csv"
    path.write_text("SIGLA ICAO AERÓDROMO;SIGLA IATA AERÓDROMO;NOME AERÓDROMO;MUNICÍPIO AERÓDROMO;ESTADO AERÓDROMO;PAÍS AERÓDROMO;AERONAVE CRÍTICA;LATITUDE;LONGITUDE\nSSOU;AIR;ARIPUANÃ;ARIPUANÃ;MT;BRASIL;1A;-10,18;-59,45\n",encoding="utf-8")
    assert read_siros(path)["SSOU"]["pais_aerodromo"]=="BRASIL"


def test_part_without_identity_sidecar_is_discarded(tmp_path):
    destination=tmp_path/"raw.csv"; destination.with_suffix(".csv.part").write_bytes(b"OLD")
    entry=download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,opener=lambda *_a,**_k:Response(b"NEW",status=200))
    assert destination.read_bytes()==b"NEW" and entry["status"]=="downloaded"


@pytest.mark.parametrize("sidecar", ['{"etag":null,"last_modified":null}','{"etag":"","last_modified":""}'])
def test_part_with_empty_identity_is_never_resumed(tmp_path,sidecar):
    destination=tmp_path/"raw.csv";partial=destination.with_suffix(".csv.part");partial.write_bytes(b"OLD")
    partial.with_suffix(".part.json").write_text(sidecar)
    seen=[]
    def opener(request,**_kwargs):
        seen.append(dict(request.header_items()));return Response(b"NEW",status=200)
    download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,opener=opener)
    assert destination.read_bytes()==b"NEW" and not any("Range" in headers for headers in seen)


@pytest.mark.parametrize(("saved","headers"),[
    ({"etag":"same"},{"Content-Type":"text/csv","Content-Range":"bytes 3-5/6"}),
    ({"last_modified":"date"},{"Content-Type":"text/csv","Content-Range":"bytes 3-5/6"}),
    ({"etag":"old"},{"Content-Type":"text/csv","Content-Range":"bytes 3-5/6","ETag":"new"}),
])
def test_resume_requires_positive_matching_response_identity(tmp_path,saved,headers):
    destination=tmp_path/"raw.csv";partial=destination.with_suffix(".csv.part");partial.write_bytes(b"OLD")
    partial.with_suffix(".part.json").write_text(__import__('json').dumps(saved))
    with pytest.raises(ValidationError,match="versão"):
        download_resumable("https://official.example/file.csv",destination,validator=lambda _p:"v",minimum_size=1,opener=lambda *_a,**_k:Response(b"NEW",status=206,headers=headers))
    assert not destination.exists() and not partial.exists()


def test_frozen_hash_and_original_metadata_are_mandatory_on_reuse(tmp_path):
    destination=tmp_path/"raw.csv"; destination.write_bytes(b"valid")
    frozen={"data_coleta_utc":"2026-08-01T00:00:00+00:00","url_final":"https://final/x","redirects":["https://final/x"],"etag":"abc","last_modified":"y"}
    digest=sha256_stream(destination)
    entry=download_resumable("https://origin/x",destination,validator=lambda _p:"v",minimum_size=1,expected_sha256=digest,frozen_entry=frozen)
    assert entry["data_coleta_utc"]==frozen["data_coleta_utc"] and entry["url_final"]==frozen["url_final"] and entry["etag"]=="abc" and "data_revalidacao_utc" in entry
    with pytest.raises(ValidationError,match="SHA-256"): download_resumable("https://origin/x",destination,validator=lambda _p:"v",minimum_size=1,expected_sha256="0"*64,frozen_entry=frozen)


def test_each_reuse_gets_new_revalidation_without_changing_collection(tmp_path):
    destination=tmp_path/"raw.csv";destination.write_bytes(b"valid");digest=sha256_stream(destination)
    frozen={"data_coleta_utc":"2026-08-01T00:00:00+00:00","url_final":"https://final/x","redirects":[],"etag":"abc","last_modified":"y"}
    first=download_resumable("https://origin/x",destination,validator=lambda _p:"v",minimum_size=1,expected_sha256=digest,frozen_entry=frozen,revalidation_utc="2026-08-18T10:00:00+00:00")
    second=download_resumable("https://origin/x",destination,validator=lambda _p:"v",minimum_size=1,expected_sha256=digest,frozen_entry=frozen,revalidation_utc="2026-08-18T10:01:00+00:00")
    assert first["data_coleta_utc"]==second["data_coleta_utc"]==frozen["data_coleta_utc"]
    assert first["data_revalidacao_utc"] < second["data_revalidacao_utc"]


def test_siros_duplicate_icao_blocks(tmp_path):
    path=tmp_path/"siros.csv";header="SIGLA ICAO AERÓDROMO;NOME AERÓDROMO;PAÍS AERÓDROMO;LATITUDE;LONGITUDE\n"
    path.write_text(header+"SSOU;A;BRASIL;-1;-2\nSSOU;B;BRASIL;-3;-4\n",encoding="utf-8")
    with pytest.raises(ValueError,match="duplicado"): read_siros(path)


def test_rotorcraft_resources_are_validated_counted_but_not_promoted(tmp_path):
    path=tmp_path/"helipontos.csv";path.write_text("Criado em: 2026-08-17\nCódigo OACI;CIAD;Nome;Latitude;Longitude\nSSHH;SP1;Heliponto;-23;-46\n",encoding="utf-8")
    assert validate_aerodromes(path)=="Criado em: 2026-08-17"
    assert read_aerodromes(path,tipo_cadastro="privativo",tipo_infraestrutura="HELIPONTO")==[]


def test_known_brazilian_destination_with_empty_country_is_resolved():
    airports=[{"aeroporto_id":"SBPA","oaci":"SBPA","ciad":"RS1","latitude":-30,"longitude":-51,"tipo_cadastro":"publico","uf":"RS"},{"aeroporto_id":"SBCT","oaci":"SBCT","ciad":"PR1","latitude":-25,"longitude":-49,"tipo_cadastro":"publico","uf":"PR"}]
    data=[]
    for y,m in months()[:6]:
        row=movement(y,m,destination="SBCT");row.update(AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_ORIGEM_UF="RS",AEROPORTO_DE_DESTINO_PAIS="",AEROPORTO_DE_DESTINO_UF="");data.append(row)
    rows,qa=build_airport_scores(airports,data)
    assert next(r for r in rows if r["aeroporto_id"]=="SBPA")["destinos_distintos"]==1
    assert qa["destinos"]["brasileiros_ligados"]==6 and not qa["destinos"].get("estrangeiros")


def test_empty_tabular_report_has_stable_header(tmp_path):
    path=tmp_path/"empty.csv";write_csv([],path,["codigo","conclusao"])
    assert path.read_bytes()==b"codigo,conclusao\n"


def test_atomic_publish_creates_missing_directories(tmp_path):
    one=tmp_path/"new/a.csv";two=tmp_path/"other/b.csv"
    publish_atomic({one:([{"a":1}],["a"]),two:([{"b":2}],["b"])})
    assert one.exists() and two.exists()


def test_atomic_publish_rolls_back_mid_promotion(tmp_path,monkeypatch):
    import ice_sul.transform.anac as module
    one=tmp_path/"a.csv";two=tmp_path/"b.csv";one.write_text("old-a\n");two.write_text("old-b\n")
    real=module.os.replace; calls=0
    def unreliable(source,target):
        nonlocal calls
        calls+=1
        if calls==4: raise OSError("promotion failure")
        return real(source,target)
    monkeypatch.setattr(module.os,"replace",unreliable)
    with pytest.raises(OSError): publish_atomic({one:([{"a":1}],["a"]),two:([{"b":2}],["b"])})
    assert one.read_text()=="old-a\n" and two.read_text()=="old-b\n"


def test_private_commercial_evidence_is_computed_from_movements():
    airport={"aeroporto_id":"SDLO","oaci":"SDLO","ciad":"BA0074","latitude":-13,"longitude":-39,"tipo_cadastro":"privativo","uf":"BA"}
    data=[]
    for y,m in months()[:6]:
        row=movement(y,m,origin="SDLO",destination="SBSV");row.update(EMPRESA_NOME="OPERADOR OFICIAL",AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_ORIGEM_UF="BA",AEROPORTO_DE_DESTINO_PAIS="BRASIL",AEROPORTO_DE_DESTINO_UF="BA");data.append(row)
    result=build_airport_scores([airport],data)[0][0]
    assert result["elegivel"] and result["operadores_observados"]=="OPERADOR OFICIAL" and result["acesso_publico_status"]=="servico_regular_comercial_observado"


def test_versioned_manifest_has_all_frozen_resources():
    import json
    root=Path(__file__).parents[1]; frozen=json.loads((root/"reports/quality/mvp-demo-2026/anac/frozen-snapshot.json").read_text())
    assert {x["id"] for x in frozen["artefatos"]}=={"movimentos","publicos","privativos","helipontos","helidecks","siros"}
    assert all(len(x["sha256"])==64 and x["data_coleta_utc"] and x["url_final"] for x in frozen["artefatos"])


def test_versioned_osrm_evidence_is_self_contained():
    import json
    path=Path(__file__).parents[1]/"reports/quality/mvp-demo-2026/anac/osrm-sensitivity-sample.json"; evidence=json.loads(path.read_text())
    required={"municipios","aeroportos","ordem_coordenadas","perfil","servidor","parametros","data_hora_utc","resposta","sha256_resposta","snapping","status","snapshot_rede"}
    assert required <= evidence.keys() and evidence["status"].startswith("exploratorio") and evidence["snapshot_rede"] is None


def test_post_cut_interdiction_blocks_operational_airport():
    status,validity,quality="Interditado","28/03/2026","indeterminado_situacao_no_corte"
    airport={"aeroporto_id":"SNVS","oaci":"SNVS","ciad":"PA1","latitude":-1,"longitude":-48,"tipo_cadastro":"publico","uf":"PA","situacao_cadastral":status,"validade":validity,"versao_fonte":"Atualizado em: 2026-08-15"}
    data=[]
    for y,m in months()[:6]:
        row=movement(y,m,origin="SNVS");row.update(AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_ORIGEM_UF="PA");data.append(row)
    result=build_airport_scores([airport],data)[0][0]
    assert result["eligibilidade_operacional"] and not result["elegivel"]
    assert result["cadastro_pos_corte"] and result["flag_qualidade"]==quality


def test_historical_validity_under_resolution_736_is_preserved_but_not_blocking():
    airport={"aeroporto_id":"SBCA","oaci":"SBCA","ciad":"PR1","latitude":-25,"longitude":-53,"tipo_cadastro":"publico","uf":"PR","situacao_cadastral":"Cadastrado","validade":"20/11/2025","versao_fonte":"Atualizado em: 2026-08-15"}
    data=[]
    for y,m in months()[:6]:
        row=movement(y,m,origin="SBCA");row.update(AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_ORIGEM_UF="PR");data.append(row)
    result=build_airport_scores([airport],data)[0][0]
    assert result["elegivel"] and result["validade"]=="20/11/2025"
    assert result["decisao_cadastral_temporal"]=="validade_historica_nao_bloqueante_resolucao_736" and not result["motivo_exclusao"]


def test_invalid_validity_has_explicit_exclusion_reason():
    airport={"aeroporto_id":"TEST","oaci":"TEST","ciad":"PR1","latitude":-25,"longitude":-53,"tipo_cadastro":"publico","uf":"PR","situacao_cadastral":"Cadastrado","validade":"not-a-date"}
    data=[movement(y,m,origin="TEST") for y,m in months()[:6]]
    result=build_airport_scores([airport],data)[0][0]
    assert not result["elegivel"] and result["motivo_exclusao"]=="formato de validade cadastral inválido"


def test_materialization_is_identical_across_two_roots(tmp_path,monkeypatch):
    root=Path(__file__).parents[1]
    import importlib.util
    spec=importlib.util.spec_from_file_location("build_anac_airports",root/"scripts/build_anac_airports.py");module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    materialize=module.materialize
    from types import SimpleNamespace
    monkeypatch.setattr(module.AnacCollector,"collect",lambda self:SimpleNamespace(status="success",errors=[],manifest_entries=[{"id":"fixture","arquivo":str(self.movements_path),"data_coleta_utc":"2026-08-01T00:00:00+00:00"}]))
    products=None
    for label in ("A","B"):
        raw=tmp_path/label/"data/raw/anac";raw.mkdir(parents=True)
        catalog="Atualizado em: 2026-08-10\nCódigo OACI;CIAD;Nome;Município;UF;LONGEOPOINT;LATGEOPOINT;Situação;Validade do Registro\nSBPA;RS1;POA;PORTO ALEGRE;RS;-51;-30;Cadastrado;01/01/2030\n"
        (raw/"cadastro-aerodromos-publicos.csv").write_text(catalog,encoding="utf-8")
        (raw/"cadastro-aerodromos-privados.csv").write_text(catalog.replace("SBPA;RS1;POA;PORTO ALEGRE;RS","SDLO;BA1;PRIV;CAIRU;BA"),encoding="utf-8")
        rotor="Criado em: 2026-08-10\nCódigo OACI;CIAD;Nome;Longitude;Latitude\nSSHH;H1;H;-51;-30\n"
        (raw/"helipontos.csv").write_text(rotor,encoding="utf-8");(raw/"helidecks.csv").write_text(rotor,encoding="utf-8")
        (raw/"aerodromos-siros.csv").write_text("SIGLA ICAO AERÓDROMO;NOME AERÓDROMO;PAÍS AERÓDROMO;LATITUDE;LONGITUDE\nSBPA;POA;BRASIL;-30;-51\nSDLO;PRIV;BRASIL;-13;-39\n",encoding="utf-8")
        fields=sorted(__import__('ice_sul.transform.anac',fromlist=['MOVEMENT_FIELDS']).MOVEMENT_FIELDS)
        with (raw/"Dados_Estatisticos.csv").open("w",encoding="utf-8",newline="") as stream:
            stream.write("Atualizado em: 2026-08-09\n");writer=__import__('csv').DictWriter(stream,fieldnames=fields,delimiter=";",lineterminator="\n");writer.writeheader()
            for y,m in months():
                row={field:"" for field in fields};row.update(movement(y,m));row.update(EMPRESA_SIGLA="OP",EMPRESA_NOME="OPERADOR",AEROPORTO_DE_ORIGEM_NOME="POA",AEROPORTO_DE_ORIGEM_UF="RS",AEROPORTO_DE_ORIGEM_PAIS="BRASIL",AEROPORTO_DE_DESTINO_NOME="PRIV",AEROPORTO_DE_DESTINO_UF="BA",AEROPORTO_DE_DESTINO_PAIS="BRASIL");writer.writerow(row)
        report=tmp_path/label/"reports/quality/mvp-demo-2026/anac";report.mkdir(parents=True)
        (report/"frozen-snapshot.json").write_text('{"artefatos":[]}')
        out=tmp_path/label/"data/interim/anac"
        materialize(raw,out,report,revalidation_utc="2026-08-18T12:00:00+00:00")
        current={p.name:p.read_bytes() for p in list(out.glob("*"))+[p for p in report.glob("*") if p.name!="frozen-snapshot.json"]}
        if products is None: products=current
        else: assert current==products


def _catalogue_csv(path: Path, rows: list[str]) -> Path:
    path.write_text(
        "Atualizado em: 2026-08-15\n"
        "Código OACI;CIAD;Nome;Município;UF;Município Servido;UF Servido;LONGEOPOINT;LATGEOPOINT;Situação;Validade do Registro\n"
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_catalogue_falls_back_to_base_municipality_and_uf_when_served_pair_is_empty(tmp_path):
    path=_catalogue_csv(tmp_path/"public.csv", ["SBCR;MS0009;CORUMBA;CORUMBÁ;MS;;;-57.671389;-19.011944;Cadastrado;"])
    row=read_aerodromes(path)[0]
    assert row["municipio_atendido"] == "CORUMBÁ"
    assert row["uf"] == "MS"


def test_catalogue_uses_served_municipality_and_served_uf_as_a_pair(tmp_path):
    path=_catalogue_csv(tmp_path/"public.csv", ["TEST;MA0002;AEROPORTO;MUNICIPIO BASE;PI;MUNICIPIO SERVIDO;MA;-47;-5;Cadastrado;"])
    row=read_aerodromes(path)[0]
    assert row["municipio_atendido"] == "MUNICIPIO SERVIDO"
    assert row["uf"] == "MA"


def test_catalogue_served_municipality_with_empty_served_uf_uses_base_uf_fallback(tmp_path):
    path=_catalogue_csv(tmp_path/"public.csv", ["TEST;MA0002;AEROPORTO;MUNICIPIO BASE;MA;MUNICIPIO SERVIDO;;-47;-5;Cadastrado;"])
    row=read_aerodromes(path)[0]
    assert row["municipio_atendido"] == "MUNICIPIO SERVIDO"
    assert row["uf"] == "MA"


def _eligible_for_gate(**updates):
    row={
        "aeroporto_id":"SBPA", "nome":"POA", "municipio_atendido":"PORTO ALEGRE", "uf":"RS",
        "latitude":-30.0, "longitude":-51.0, "tipo_cadastro":"publico",
        "arquivo_movimentos":"data/raw/anac/Dados_Estatisticos.csv",
        "arquivo_cadastro":"data/raw/anac/cadastro-aerodromos-publicos.csv",
        "versao_movimentos":"Atualizado em: 2026-08-09", "versao_cadastro":"Atualizado em: 2026-08-15",
        "eligibilidade_operacional":True, "elegivel":True,
    }
    row.update(updates)
    return row


def test_publication_integrity_rejects_empty_territorial_fields_and_invalid_uf():
    qa={"coverage_complete":True,"reconciliacoes":{"a":True,"b":True}}
    result=assess_publication_integrity([_eligible_for_gate(municipio_atendido="",uf="")],qa)
    assert result["campos_territoriais_ausentes"]["elegiveis"] == {"municipio_atendido":1,"uf":1}
    assert not result["portoes_publicacao"]["campos_obrigatorios_elegiveis"]
    assert not result["portoes_publicacao"]["ufs_validas"]


def test_publication_integrity_requires_reconciliations_and_unique_ids():
    rows=[_eligible_for_gate(),_eligible_for_gate()]
    qa={"coverage_complete":True,"reconciliacoes":{"a":False}}
    result=assess_publication_integrity(rows,qa)
    assert not result["portoes_publicacao"]["ids_unicos"]
    assert not result["portoes_publicacao"]["reconciliacoes"]


def test_publication_integrity_all_gates_green_for_valid_eligible_airport():
    qa={"coverage_complete":True,"reconciliacoes":{"a":True,"b":True}}
    result=assess_publication_integrity([_eligible_for_gate()],qa)
    assert all(result["portoes_publicacao"].values())
    assert result["campos_territoriais_ausentes"]["elegiveis"] == {"municipio_atendido":0,"uf":0}
