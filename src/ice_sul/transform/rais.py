"""Transformação estrita dos microdados RAIS 2024 VINC_PUB."""
from __future__ import annotations
import csv, re, tempfile, unicodedata
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Iterator, Mapping, TextIO

ALIASES={
 "municipio":("municípiotrabcódigo","municípiocódigo"),
 "cnae":("cnae20classecódigo",), "natureza":("naturezajurídicacódigo",),
 "ativo":("indvínculoativo3112código",), "uf":("uf","sigla uf"),
}
UF_PREFIX={"12":"AC","27":"AL","13":"AM","16":"AP","29":"BA","23":"CE","53":"DF","32":"ES","52":"GO","21":"MA","31":"MG","50":"MS","51":"MT","15":"PA","25":"PB","26":"PE","22":"PI","41":"PR","33":"RJ","24":"RN","11":"RO","14":"RR","43":"RS","42":"SC","28":"SE","35":"SP","17":"TO"}

def _normal(v:str)->str:
 return re.sub(r"[^a-z0-9]+","",unicodedata.normalize("NFKD",v).encode("ascii","ignore").decode().lower())

def resolve_columns(fieldnames:Iterable[str])->dict[str,str]:
 normalized={_normal(n):n for n in fieldnames}; out={}
 for target, aliases in ALIASES.items():
  for alias in aliases:
   if _normal(alias) in normalized: out[target]=normalized[_normal(alias)]; break
 missing={"municipio","cnae","natureza","ativo"}-out.keys()
 if missing: raise ValueError(f"colunas VINC_PUB RAIS 2024 ausentes: {sorted(missing)}")
 return out

def _strict(value:object, pattern:str, field:str)->str:
 text=str(value if value is not None else "").strip()
 if not re.fullmatch(pattern,text): raise ValueError(f"{field} inválido: {value!r}")
 return text

def parse_active(value:object)->str: return _strict(value,r"[01]","indicador de vínculo ativo")
def parse_municipality(value:object)->str: return _strict(value,r"\d{6}","código municipal")
def parse_cnae(value:object)->str:
 value=_strict(value,r"\d{5}","CNAE 2.0 classe")
 if value[:2]=="00": raise ValueError(f"CNAE 2.0 classe inválida: {value!r}")
 return value
def parse_legal_nature(value:object)->str:
 value=_strict(value,r"\d{4}","Natureza Jurídica")
 if value[0] not in "12345": raise ValueError(f"Natureza Jurídica grupo desconhecido: {value!r}")
 return value
def cnae_division(value:object)->str: return parse_cnae(value)[:2]
def is_public_administration(cnae:object,legal_nature:object)->bool:
 return parse_cnae(cnae)[:2]=="84" or parse_legal_nature(legal_nature).startswith("1")

def load_municipality_map(reference_csv:Path)->dict[str,str]:
 with reference_csv.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
 mapping={}
 for row in rows:
  ibge=_strict(row.get("municipio_id"),r"\d{7}","municipio_id canônico"); rais=ibge[:6]
  if rais in mapping and mapping[rais]!=ibge: raise ValueError(f"chave RAIS ambígua: {rais}")
  mapping[rais]=ibge; mapping[ibge]=ibge
 return mapping

def _detect_encoding(path:Path)->str:
 raw=path.open("rb").read(65536)
 for enc in ("utf-8-sig","cp1252"):
  try: raw.decode(enc); return enc
  except UnicodeDecodeError: pass
 raise ValueError("encoding do .comt não é UTF-8 nem Windows-1252")

def read_comt(path:Path)->tuple[csv.DictReader,TextIO,dict[str,str]]:
 enc=_detect_encoding(path); stream=path.open(encoding=enc,newline=""); sample=stream.read(65536)
 try: dialect=csv.Sniffer().sniff(sample,delimiters=";|\t")
 except csv.Error as exc: stream.close(); raise ValueError("delimitador .comt inválido") from exc
 stream.seek(0); reader=csv.DictReader(stream,dialect=dialect)
 if not reader.fieldnames: stream.close(); raise ValueError(".comt sem cabeçalho")
 return reader,stream,{"encoding":enc,"delimitador":dialect.delimiter}

def safe_member(name:str)->Path:
 posix=PurePosixPath(name); windows=PureWindowsPath(name)
 if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or ".." in windows.parts:
  raise ValueError(f"caminho inseguro no .7z: {name}")
 return Path(*posix.parts)

@contextmanager
def extracted_comt(archive:Path)->Iterator[Path]:
 import py7zr
 if archive.suffix.lower()!=".7z": raise ValueError(f"arquivo RAIS não é .7z: {archive}")
 with py7zr.SevenZipFile(archive) as seven:
  names=seven.getnames(); [safe_member(n) for n in names]
  candidates=[n for n in names if n.lower().endswith(".comt")]
  if len(candidates)!=1: raise ValueError(f"esperado exatamente um .comt; encontrados: {candidates}")
  member=candidates[0]
  with tempfile.TemporaryDirectory(prefix="sit-rais-") as d:
   seven.extract(path=d,targets=[member]); path=Path(d)/safe_member(member)
   if not path.is_file() or path.stat().st_size==0: raise ValueError("membro .comt vazio/não extraível")
   yield path

@dataclass
class RaisResult:
 private_employment:list[dict[str,object]]
 diversification:list[dict[str,object]]
 quality:dict[str,object]

def transform_rows(rows:Iterable[Mapping[str,object]],*,columns:Mapping[str,str],year:int,file_uf:str,
 municipality_map:Mapping[str,str],south_municipalities:Iterable[str]=(),source_file:str="fixture.7z")->RaisResult:
 totals=Counter(); sectors=defaultdict(Counter); qa=Counter(); unmatched=Counter(); linked=set(); active_freq=Counter(); file_uf=file_uf.upper()
 for row in rows:
  qa["vinculos_lidos"]+=1
  try: active=parse_active(row[columns["ativo"]])
  except ValueError: qa["valores_invalidos"]+=1; qa["falhas_campo_ativo"]+=1; raise
  active_freq[active]+=1
  if active=="0": qa["vinculos_inativos_excluidos"]+=1; continue
  qa["vinculos_ativos_lidos"]+=1
  try: raw=parse_municipality(row[columns["municipio"]]); cnae=parse_cnae(row[columns["cnae"]]); nature=parse_legal_nature(row[columns["natureza"]])
  except ValueError as exc:
   qa["valores_invalidos"]+=1; raise
  code=municipality_map.get(raw)
  if code is None: unmatched[raw]+=1; qa["vinculos_municipio_nao_ligado"]+=1; continue
  expected=UF_PREFIX.get(code[:2])
  if expected!=file_uf: raise ValueError(f"UF do arquivo inconsistente para {raw}->{code}: {file_uf} != {expected}")
  if "uf" in columns and str(row[columns["uf"]]).strip().upper()!=file_uf: raise ValueError("UF da coluna diverge do arquivo")
  linked.add(code); division=cnae[:2]
  if division=="84" or nature.startswith("1"): qa["vinculos_administracao_publica_excluidos"]+=1; continue
  totals[code]+=1; sectors[code][division]+=1; qa["vinculos_privados_elegiveis"]+=1
 south=list(south_municipalities)
 if len(south)!=len(set(south)): raise ValueError("universo Sul contém códigos duplicados")
 provenance={"fonte_id":"MTE-PDET-RAIS","fonte_arquivo":source_file,"versao_fonte":f"RAIS {year} VINC_PUB"}
 private=[{"municipio_id":c,"empregos_formais_privados":n,"periodo_referencia":str(year),"flag_qualidade":"observado",**provenance} for c,n in sorted(totals.items())]
 diagnostic=[]
 for code in sorted(south):
  total=totals.get(code,0); value=None if total==0 else 1-sum((n/total)**2 for n in sectors[code].values())
  diagnostic.append({"municipio_id":code,"indicador_id":"MER-DIAG-01","valor_bruto":value,"periodo_referencia":str(year),"flag_qualidade":"ausente" if value is None else "zero_observado" if value==0 else "observado","motivo_qualidade":"sem_vinculo_privado" if value is None else "",**provenance})
 quality={"ano":year,**dict(qa),"frequencias_vinculo_ativo":dict(sorted(active_freq.items())),"valores_invalidos":qa["valores_invalidos"],"uf_processada":file_uf,"municipios_ligados":len(linked),"codigos_nao_ligados":dict(sorted(unmatched.items())),"municipios_nao_ligados":len(unmatched),"soma_municipal":sum(totals.values())}
 quality["reconciliacao_ok"]=quality["soma_municipal"]==qa["vinculos_privados_elegiveis"]
 quality["reconciliacao_territorial_ok"]=qa["vinculos_ativos_lidos"]==qa["vinculos_municipio_nao_ligado"]+qa["vinculos_administracao_publica_excluidos"]+qa["vinculos_privados_elegiveis"]
 return RaisResult(private,diagnostic,quality)

def transform_archive(archive:Path,*,file_uf:str,municipality_map:Mapping[str,str],year:int=2024,south_municipalities:Iterable[str]=())->RaisResult:
 with extracted_comt(archive) as comt:
  reader,stream,metadata=read_comt(comt)
  try: result=transform_rows(reader,columns=resolve_columns(reader.fieldnames or []),year=year,file_uf=file_uf,municipality_map=municipality_map,south_municipalities=south_municipalities,source_file=archive.name)
  finally: stream.close()
 result.quality.update(metadata,arquivo=archive.name,membro_comt=comt.name); return result
