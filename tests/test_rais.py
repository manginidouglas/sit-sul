import csv,json,zipfile
from pathlib import Path
from urllib.error import URLError
import openpyxl,py7zr,pytest
from ice_sul.extract.contracts import CollectionStatus
from ice_sul.extract.rais import (DE_PARA_URL,OFFICIAL_HOST,FTPTransportError,RaisArchive,RaisCollector,OfficialRoutesUnavailable,
 REGIONAL_PARTITIONS,UF_CODES,_download_archive,_download_validated,_validate_open_archive,archives_from_listing,content_type,discover_de_para_url,
 discover_official_archives,download_de_para,parse_archive_listing,parse_archive_name,partition_coverage,reused_manifest,sha256_file,validate_7z,validate_archive_coverage,validate_xlsx,view_to_download)
from ice_sul.transform.rais import (UF_PREFIX,cnae_division,is_public_administration,parse_active,parse_cnae,parse_legal_nature,parse_municipality,
 read_comt,resolve_columns,transform_archive,transform_rows)

HEADERS=["indvínculoativo3112código","cnae20classecódigo","naturezajurídicacódigo","municípiotrabcódigo"]
PREFIX={uf:prefix for prefix,uf in UF_PREFIX.items()}

def workbook(path:Path,*,sheet="VINC_PUB",fields=None):
 wb=openpyxl.Workbook();ws=wb.active;ws.title=sheet;ws.append(["De","Para"])
 for value in fields or ["cnae20classecódigo","indvínculoativo3112código","municípiotrabcódigo","naturezajurídicacódigo"]:ws.append(["origem",value])
 wb.save(path);wb.close();return path

def archive(path:Path,rows=None,members=1):
 text=path.parent/(path.stem+".comt");text.write_text(";".join(HEADERS)+"\n"+"\n".join(";".join(r) for r in (rows or [["1","62015","2062","410690"]]))+"\n",encoding="utf-8")
 with py7zr.SevenZipFile(path,"w") as z:
  for i in range(members):z.write(text,arcname=f"vinc_{i}.comt")
 text.unlink();return path

def full_listing():return [f"RAIS_VINC_PUB_{uf}.7z" for uf in UF_CODES]

def offline_tree(tmp_path:Path):
 raw=tmp_path/"raw";raw.mkdir(); interim=tmp_path/"interim";quality=tmp_path/"quality"
 workbook(raw/"De-Para Microdados.xlsx")
 south=[];all_codes=[];specs=[]
 for uf in UF_CODES:
  count=397 if uf in {"PR","SC","RS"} else 1
  codes=[f"{PREFIX[uf]}{i:04d}{i%10}" for i in range(1,count+1)]
  all_codes+=codes
  if uf in {"PR","SC","RS"}:south+=codes
  rows=[["1","62015","2062",codes[0][:6]],["0","62015","2062",codes[0][:6]],["1","84116","1015",codes[0][:6]]]
  if uf=="PR":rows.append(["1","47113","2062",codes[0][:6]])
  if uf=="RS":rows=[["1","84116","1015",codes[0][:6]]]
  name=f"RAIS_VINC_PUB_{uf}.7z";archive(raw/name,rows);specs.append(RaisArchive(uf,(uf,),f"https://{OFFICIAL_HOST}/pdet/microdados/RAIS/2024/{name}"))
 (raw/"municipios-ibge.json").write_text(json.dumps([{"id":int(c)} for c in all_codes]))
 reference=tmp_path/"south.csv";reference.write_text("municipio_id\n"+"\n".join(south)+"\n")
 return RaisCollector(raw,interim,quality,reference,specs),raw,interim,quality

def partitioned_offline_tree(tmp_path:Path,partitions:dict[str,tuple[str,...]]):
 raw=tmp_path/"raw";raw.mkdir(); interim=tmp_path/"interim";quality=tmp_path/"quality"
 workbook(raw/"De-Para Microdados.xlsx")
 south=[];all_codes=[];codes_by_uf={};specs=[]
 for uf in UF_CODES:
  count=397 if uf in {"PR","SC","RS"} else 1
  codes=[f"{PREFIX[uf]}{i:04d}{i%10}" for i in range(1,count+1)]
  codes_by_uf[uf]=codes;all_codes+=codes
  if uf in {"PR","SC","RS"}:south+=codes
 for partition_id,covered_ufs in partitions.items():
  rows=[]
  for uf in covered_ufs:
   raw_code=codes_by_uf[uf][0][:6]
   rows.append(["1","62015","2062",raw_code])
   rows.append(["0","62015","2062",raw_code])
   rows.append(["1","84116","1015",raw_code])
   if uf=="PR":rows.append(["1","47113","2062",raw_code])
  name=f"RAIS_VINC_PUB_{partition_id}.7z";archive(raw/name,rows)
  specs.append(RaisArchive(partition_id,tuple(covered_ufs),f"https://{OFFICIAL_HOST}/pdet/microdados/RAIS/2024/{name}"))
 (raw/"municipios-ibge.json").write_text(json.dumps([{"id":int(c)} for c in all_codes]))
 reference=tmp_path/"south.csv";reference.write_text("municipio_id\n"+"\n".join(south)+"\n")
 return RaisCollector(raw,interim,quality,reference,specs),raw,interim,quality

# Workbook real e descoberta do link.
def test_valid_workbook_confirms_sheet_fields_hash_and_size(tmp_path):
 info=validate_xlsx(workbook(tmp_path/"valid.xlsx"));assert info["abas"]==["VINC_PUB"];assert set(info["campos_confirmados"])>=set(HEADERS[1:]);assert len(info["sha256"])==64
@pytest.mark.parametrize("kind",["html","minimal_zip","corrupt"])
def test_workbook_rejects_nonfunctional_files(tmp_path,kind):
 p=tmp_path/"bad.xlsx"
 if kind=="html":p.write_text("<html>error</html>")
 elif kind=="minimal_zip":
  with zipfile.ZipFile(p,"w") as z:z.writestr("xl/workbook.xml","<workbook/>")
 else:p.write_bytes(b"PK\x03\x04broken")
 with pytest.raises(ValueError):validate_xlsx(p)
def test_workbook_rejects_missing_sheet_or_fields(tmp_path):
 with pytest.raises(ValueError,match="VINC_PUB"):validate_xlsx(workbook(tmp_path/"sheet.xlsx",sheet="OTHER"))
 with pytest.raises(ValueError,match="campos"):validate_xlsx(workbook(tmp_path/"fields.xlsx",fields=["cnae20classecódigo"]))
def test_depara_view_is_converted_and_external_rejected():
 html=f'<a href="{DE_PARA_URL.replace("/@@download/file","/view")}">De-Para</a>'
 assert discover_de_para_url(html)==DE_PARA_URL
 assert view_to_download(DE_PARA_URL)==DE_PARA_URL
 with pytest.raises(ValueError,match="domínio"):view_to_download("https://evil.test/de-para.xlsx/view")
def test_depara_direct_download_route_is_preferred(tmp_path,monkeypatch):
 called=[]
 def fake(url,destination,**kwargs):called.append(url);workbook(destination);return {"url":url,"validacao":validate_xlsx(destination)}
 monkeypatch.setattr("ice_sul.extract.rais._download_validated",fake)
 entry,attempts=download_de_para(tmp_path/"raw.xlsx");assert attempts==[];assert called==[DE_PARA_URL];assert entry["url"]==DE_PARA_URL

# 7-Zip: semântica CRC, todos os membros e contêineres inválidos.
class FakeSeven:
 def __init__(self,names=("vinc.comt",),testzip=None,test=None):self.names=names;self.bad=testzip;self.crc=test
 def getnames(self):return list(self.names)
 def testzip(self):return self.bad
 def test(self):return self.crc
@pytest.mark.parametrize("crc",[True,None])
def test_7z_crc_true_or_absent_is_accepted_by_available_test(crc):assert _validate_open_archive(FakeSeven(test=crc))["crc_result"] is crc
def test_7z_crc_false_and_bad_member_are_rejected():
 with pytest.raises(ValueError,match="CRC.*falhou"):_validate_open_archive(FakeSeven(test=False))
 with pytest.raises(ValueError,match="CRC inválido"):_validate_open_archive(FakeSeven(testzip="vinc.comt",test=True))
@pytest.mark.parametrize("names",[("vinc.comt","../evil.txt"),("vinc.comt","/absolute.txt"),("readme.txt",),("a.comt","b.comt")])
def test_7z_rejects_unsafe_or_wrong_members(names):
 with pytest.raises(ValueError):_validate_open_archive(FakeSeven(names=names))
def test_7z_valid_without_crc_is_extractable(tmp_path):assert validate_7z(archive(tmp_path/"valid.7z"))["crc_result"] is None
@pytest.mark.parametrize("payload",[b"<html>503</html>",b"7z\xbc\xaf\x27\x1c"])
def test_7z_rejects_html_and_truncation(tmp_path,payload):
 p=tmp_path/"bad.7z";p.write_bytes(payload)
 with pytest.raises(ValueError):validate_7z(p)

# Listagem oficial e fallback.
def test_complete_listing_preserves_names_and_excludes_establishments():
 specs=parse_archive_listing(full_listing()+["RAIS_ESTAB_PUB_PR.7z"],source_url=f"https://{OFFICIAL_HOST}/x/");assert len(specs)==27;assert specs[0].filename in full_listing()
@pytest.mark.parametrize("items,match",[(full_listing()[:-1],"ausentes"),(full_listing()+[full_listing()[0]],"duplicada"),(full_listing()+["RAIS_VINC_PUB_PR_2023.7z"],"inesperado"),(full_listing()+["odd.7z"],"inesperado")])
def test_listing_rejects_missing_duplicate_other_year_or_unexpected(items,match):
 with pytest.raises(ValueError,match=match):archives_from_listing(items)
def test_listing_rejects_external_url_or_host():
 with pytest.raises(ValueError,match="externa"):archives_from_listing(full_listing()+["https://evil.test/RAIS_VINC_PUB_PR.7z"])
 with pytest.raises(ValueError,match="externo"):parse_archive_listing(full_listing(),source_url="https://evil.test/")
def test_discovery_https_success(monkeypatch):
 monkeypatch.setattr("ice_sul.extract.rais._https_listing",lambda:(full_listing(),{"metodo":"HTTPS","status":"success"}));specs,attempts=discover_official_archives();assert len(specs)==27 and attempts[-1]["status"]=="success"
def test_discovery_https_failure_ftp_mlsd_success(monkeypatch):
 monkeypatch.setattr("ice_sul.extract.rais._https_listing",lambda:(_ for _ in ()).throw(URLError("down")))
 monkeypatch.setattr("ice_sul.extract.rais._ftp_listing",lambda:(full_listing(),[{"metodo":"FTP MLSD","status":"success"}]))
 specs,attempts=discover_official_archives();assert len(specs)==27;assert [a["metodo"] for a in attempts][:2]==["HTTPS","FTP MLSD"]
def test_ftp_listing_falls_back_to_nlst(monkeypatch):
 class FTP:
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def connect(self,*a,**k):pass
  def login(self):pass
  def cwd(self,*a):pass
  def mlsd(self):raise ftplib.error_perm("500 unsupported")
  def nlst(self):return full_listing()
 import ftplib
 monkeypatch.setattr("ice_sul.extract.rais.ftplib.FTP",FTP)
 from ice_sul.extract.rais import _ftp_listing
 names,attempts=_ftp_listing();assert names==full_listing();assert [a["status"] for a in attempts]==["failed","success"]
def test_discovery_all_routes_fail(monkeypatch):
 import ftplib
 monkeypatch.setattr("ice_sul.extract.rais._https_listing",lambda:(_ for _ in ()).throw(URLError("down")))
 monkeypatch.setattr("ice_sul.extract.rais._ftp_listing",lambda:(_ for _ in ()).throw(ftplib.error_temp("down")))
 with pytest.raises(OfficialRoutesUnavailable) as exc:discover_official_archives()
 assert len(exc.value.attempts)==2

# Hash streaming, MIME, reuso e promoção somente após validação.
def test_reuse_hashes_streaming_and_mime(tmp_path,monkeypatch):
 p=tmp_path/"x.json";p.write_text("{}")
 monkeypatch.setattr(Path,"read_bytes",lambda self:(_ for _ in ()).throw(AssertionError("not streaming")))
 entry=reused_manifest(p,url="https://example.test/x",uf="BR",validation={"ok":True});assert entry["status"]=="reused";assert entry["content_type"]=="application/json";assert entry["sha256"]==sha256_file(p)
def test_invalid_reused_raw_fails_validation(tmp_path):
 p=tmp_path/"raw.7z";p.write_text("html")
 with pytest.raises(ValueError):reused_manifest(p,url="x",uf="PR",validation=validate_7z(p))
def test_invalid_download_never_promotes_part(tmp_path,monkeypatch):
 class Response:
  status=200;url=DE_PARA_URL;headers={"Content-Type":"text/html"}
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def read(self,n=-1):out=getattr(self,"out",False);self.out=True;return b"<html>bad</html>" if not out else b""
 class Opener:
  def open(self,*a,**k):return Response()
 monkeypatch.setattr("ice_sul.extract.rais.build_opener",lambda *a:Opener());dest=tmp_path/"raw.xlsx"
 with pytest.raises(ValueError):_download_validated(DE_PARA_URL,dest,uf="BR",validator=validate_xlsx)
 assert not dest.exists() and not (tmp_path/"raw.xlsx.part").exists()

# Parsers estritos e transformações/proveniência.
@pytest.mark.parametrize("func,value",[(parse_active,"1x"),(parse_active,"2"),(parse_municipality,"410690x"),(parse_municipality,"410.690"),(parse_cnae,"47abc"),(parse_cnae,"47"),(parse_cnae,"471130"),(parse_legal_nature,"2x0x6x2"),(parse_legal_nature,"20.62"),(parse_legal_nature,""),(parse_legal_nature,"9999")])
def test_strict_parsers_reject_entire_invalid_value(func,value):
 with pytest.raises(ValueError):func(value)
def test_cnae_class_field_uses_official_width_not_subclass_width():
 assert parse_cnae("07235")=="07235";assert cnae_division("07235")=="07";assert cnae_division("84116")=="84"
 with pytest.raises(ValueError):parse_cnae("0723501")
 for invalid in ("7235","072350","07.23-5","07A35","00000",""):
  with pytest.raises(ValueError):parse_cnae(invalid)
 assert is_public_administration("84116","2062") is True
def test_active_municipality_and_legal_nature_operational_formats_are_strict():
 assert [parse_active(v) for v in ("0","1")]==["0","1"]
 assert parse_municipality("010001")=="010001"
 with pytest.raises(ValueError):parse_municipality("4106902")
 assert parse_legal_nature("1015")=="1015";assert parse_legal_nature("2062")=="2062"
 for invalid in ("","062","02062","6A62","20.62","9999"):
  with pytest.raises(ValueError):parse_legal_nature(invalid)
def test_versioned_layout_evidence_records_exact_depara_rows_and_limitations():
 evidence=json.loads(Path("reports/quality/mvp-demo-2026/rais/layout-campos-confirmados.json").read_text())
 fields={item["nome_novo"]:item for item in evidence["campos"]}
 assert fields["cnae20classecódigo"]["linha"]==10
 assert fields["cnae20classecódigo"]["regra_parser_adotada"]==r"\d{5}"
 assert fields["indvínculoativo3112código"]["dominio_confirmado_no_de_para"] is None
 assert evidence["workbook"]["sha256"]=="4be7a7421ce44e40c4b18ea044c624e16775a5d0e3429dac18acb6afd7545117"
def test_transform_contract_and_active_frequencies(tmp_path):
 p=archive(tmp_path/"PR.7z",[["1","47113","2062","410690"],["1","62015","2062","410690"],["0","62015","2062","410690"]]);result=transform_archive(p,allowed_ufs=("PR",),municipality_map={"410690":"4106902"},south_municipalities=["4106902","4100001"])
 assert set(result.private_employment[0])=={"municipio_id","empregos_formais_privados","periodo_referencia","flag_qualidade","fonte_id","fonte_arquivo","versao_fonte"};assert result.private_employment[0]["flag_qualidade"]=="observado"
 assert set(result.diversification[0])=={"municipio_id","indicador_id","valor_bruto","periodo_referencia","flag_qualidade","motivo_qualidade","fonte_id","fonte_arquivo","versao_fonte"};assert result.quality["frequencias_vinculo_ativo"]=={"0":1,"1":2}

# Execução nacional integral offline e portões atômicos.
def test_full_offline_collector_27_ufs_publishes_atomically(tmp_path,monkeypatch):
 collector,raw,interim,quality=offline_tree(tmp_path);monkeypatch.setattr("ice_sul.extract.rais.build_opener",lambda *a:(_ for _ in ()).throw(AssertionError("network")))
 result=collector.collect();assert result.status==CollectionStatus.SUCCESS
 qa=json.loads((quality/"qa.json").read_text());assert len(qa["ufs_esperadas"])==len(qa["ufs_processadas"])==27;assert qa["coverage_complete"] is True;assert not qa["codigos_nao_ligados"]
 with (interim/"mer_diag_01.csv").open() as f:diag=list(csv.DictReader(f))
 with (interim/"emprego_privado_municipal.csv").open() as f:private=list(csv.DictReader(f))
 assert len(diag)==1191;assert {r["flag_qualidade"] for r in diag}>={"ausente","zero_observado","observado"};assert all(r["fonte_arquivo"] for r in diag+private);assert all((interim/n).exists() for n in ("mer_diag_01.csv","emprego_privado_municipal.csv"))
@pytest.mark.parametrize("mutation",["missing_uf","duplicate_uf","unmatched","invalid_active","invalid_cnae","invalid_nature","invalid_raw"])
def test_national_gate_failure_leaves_no_csv(tmp_path,mutation):
 collector,raw,interim,quality=offline_tree(tmp_path)
 if mutation=="missing_uf":collector.archives=collector.archives[:-1]
 elif mutation=="duplicate_uf":collector.archives[-1]=collector.archives[0]
 else:
  spec=collector.archives[0];path=raw/spec.filename;path.unlink()
  if mutation=="invalid_raw":path.write_text("html")
  else:
   values={"unmatched":["1","62015","2062","999999"],"invalid_active":["1x","62015","2062","120001"],"invalid_cnae":["1","47abc","2062","120001"],"invalid_nature":["1","62015","2x0x6x2","120001"]}[mutation];archive(path,[values])
 result=collector.collect();assert result.status==CollectionStatus.FAILED_VALIDATION;assert not (interim/"emprego_privado_municipal.csv").exists();assert not (interim/"mer_diag_01.csv").exists();assert json.loads((quality/"qa.json").read_text())["coverage_complete"] is False
def test_post_transform_duplicate_failure_is_collection_result_without_outputs(tmp_path,monkeypatch):
 collector,raw,interim,quality=offline_tree(tmp_path)
 original=transform_archive;first={"result":None}
 def duplicate(*args,**kwargs):
  result=original(*args,**kwargs)
  if result.private_employment:
   if first["result"] is None:first["result"]=result.private_employment[0]["municipio_id"]
   else:result.private_employment[0]["municipio_id"]=first["result"]
  return result
 monkeypatch.setattr("ice_sul.extract.rais.transform_archive",duplicate)
 result=collector.collect();assert result.status==CollectionStatus.FAILED_VALIDATION;assert not (interim/"emprego_privado_municipal.csv").exists();assert json.loads((quality/"qa.json").read_text())["coverage_complete"] is False

# Classificação: transporte bloqueado é diferente de bytes/esquema inválidos.
def test_https_and_ftp_network_failures_are_wrapped_as_blocked_source(tmp_path,monkeypatch):
 collector,raw,interim,quality=offline_tree(tmp_path);spec=collector.archives[0];(raw/spec.filename).unlink()
 monkeypatch.setattr("ice_sul.extract.rais._download_validated",lambda *a,**k:(_ for _ in ()).throw(URLError("HTTPS down")))
 monkeypatch.setattr("ice_sul.extract.rais._download_ftp_validated",lambda *a,**k:(_ for _ in ()).throw(FTPTransportError("FTP network unreachable")))
 result=collector.collect();assert result.status==CollectionStatus.BLOCKED_SOURCE;assert [a["metodo"] for a in result.manifest_entries[-2:]]==["HTTPS","FTP RETR"];assert not (interim/"mer_diag_01.csv").exists()
def test_https_failure_and_ftp_temporary_error_are_blocked(tmp_path,monkeypatch):
 spec=RaisArchive("PR",("PR",),f"https://{OFFICIAL_HOST}/RAIS_VINC_PUB_PR.7z")
 monkeypatch.setattr("ice_sul.extract.rais._download_validated",lambda *a,**k:(_ for _ in ()).throw(URLError("down")))
 monkeypatch.setattr("ice_sul.extract.rais._download_ftp_validated",lambda *a,**k:(_ for _ in ()).throw(FTPTransportError("421 temporary")))
 with pytest.raises(OfficialRoutesUnavailable) as caught:_download_archive(spec,tmp_path/spec.filename)
 assert len(caught.value.attempts)==2
def test_https_failure_then_valid_ftp_succeeds(tmp_path,monkeypatch):
 spec=RaisArchive("PR",("PR",),f"https://{OFFICIAL_HOST}/RAIS_VINC_PUB_PR.7z");destination=tmp_path/spec.filename
 monkeypatch.setattr("ice_sul.extract.rais._download_validated",lambda *a,**k:(_ for _ in ()).throw(URLError("down")))
 def valid_ftp(spec,path):archive(path);return {"metodo":"FTP RETR","url":"ftp://official","validacao":validate_7z(path)}
 monkeypatch.setattr("ice_sul.extract.rais._download_ftp_validated",valid_ftp)
 entry=_download_archive(spec,destination);assert entry["metodo"]=="FTP RETR";assert destination.exists();assert len(entry["tentativas_anteriores"])==1
def test_invalid_bytes_from_https_or_ftp_are_failed_validation_not_blocked(tmp_path,monkeypatch):
 spec=RaisArchive("PR",("PR",),f"https://{OFFICIAL_HOST}/RAIS_VINC_PUB_PR.7z")
 monkeypatch.setattr("ice_sul.extract.rais._download_validated",lambda *a,**k:(_ for _ in ()).throw(ValueError("assinatura inválida")))
 with pytest.raises(ValueError,match="assinatura"):_download_archive(spec,tmp_path/"https.7z")
 monkeypatch.setattr("ice_sul.extract.rais._download_validated",lambda *a,**k:(_ for _ in ()).throw(URLError("down")))
 monkeypatch.setattr("ice_sul.extract.rais._download_ftp_validated",lambda *a,**k:(_ for _ in ()).throw(ValueError("7-Zip truncado")))
 with pytest.raises(ValueError,match="truncado"):_download_archive(spec,tmp_path/"ftp.7z")

# Partições territoriais: arquivos estaduais, regionais ou nacional.
def test_partition_parser_supports_state_regional_and_national():
 state=parse_archive_name("RAIS_VINC_PUB_PR_2024.7z")
 regional=parse_archive_name("RAIS_VINC_PUB_SUL.7z")
 national=parse_archive_name("RAIS_VINC_PUB_BRASIL.7z")
 assert state.partition_id=="PR" and state.covered_ufs==("PR",)
 assert regional.covered_ufs==("PR","SC","RS")
 assert set(national.covered_ufs)==set(UF_CODES)
 assert partition_coverage("CENTRO-OESTE")==REGIONAL_PARTITIONS["CENTRO_OESTE"]


def test_partition_coverage_rejects_missing_overlap_and_unknown_partition():
 with pytest.raises(ValueError,match="UFs ausentes"):
  validate_archive_coverage([RaisArchive("SUL",REGIONAL_PARTITIONS["SUL"],"https://official/RAIS_VINC_PUB_SUL.7z")])
 regional=[RaisArchive(name,ufs,f"https://official/RAIS_VINC_PUB_{name}.7z") for name,ufs in REGIONAL_PARTITIONS.items()]
 with pytest.raises(ValueError,match="UFs sobrepostas"):
  validate_archive_coverage(regional+[RaisArchive("PR",("PR",),"https://official/RAIS_VINC_PUB_PR.7z")])
 with pytest.raises(ValueError,match="desconhecida"):
  parse_archive_name("RAIS_VINC_PUB_DESCONHECIDA.7z")


def test_full_offline_collector_regional_partitions(tmp_path,monkeypatch):
 collector,raw,interim,quality=partitioned_offline_tree(tmp_path,REGIONAL_PARTITIONS)
 monkeypatch.setattr("ice_sul.extract.rais.build_opener",lambda *a:(_ for _ in ()).throw(AssertionError("network")))
 result=collector.collect();assert result.status==CollectionStatus.SUCCESS
 qa=json.loads((quality/"qa.json").read_text())
 assert len(qa["particoes_processadas"])==6;assert len(qa["ufs_cobertas"])==27;assert qa["coverage_complete"] is True
 with (interim/"mer_diag_01.csv").open() as f:diag=list(csv.DictReader(f))
 assert len(diag)==1191;assert {r["fonte_arquivo"] for r in diag}=={"RAIS_VINC_PUB_SUL.7z"}
 assert {r["flag_qualidade"] for r in diag}>={"ausente","zero_observado","observado"}


def test_single_national_partition_publishes_complete_coverage(tmp_path,monkeypatch):
 collector,raw,interim,quality=partitioned_offline_tree(tmp_path,{"BRASIL":UF_CODES})
 monkeypatch.setattr("ice_sul.extract.rais.build_opener",lambda *a:(_ for _ in ()).throw(AssertionError("network")))
 result=collector.collect();assert result.status==CollectionStatus.SUCCESS
 qa=json.loads((quality/"qa.json").read_text())
 assert qa["particoes_processadas"]==["BRASIL"];assert len(qa["ufs_cobertas"])==27;assert qa["coverage_complete"] is True
 with (interim/"mer_diag_01.csv").open() as f:diag=list(csv.DictReader(f))
 assert len(diag)==1191;assert {r["fonte_arquivo"] for r in diag}=={"RAIS_VINC_PUB_BRASIL.7z"}


def test_multi_uf_partition_rejects_municipality_outside_coverage(tmp_path):
 p=archive(tmp_path/"SUL.7z",[["1","62015","2062","350000"]])
 with pytest.raises(ValueError,match="fora da cobertura"):
  transform_archive(p,allowed_ufs=REGIONAL_PARTITIONS["SUL"],municipality_map={"350000":"3500001"})
