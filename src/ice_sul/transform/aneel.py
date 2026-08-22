"""Parsing, validação e territorialização municipal de DEC/FEC da ANEEL."""
from __future__ import annotations
import csv, math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable

PERIODO="2025"; INDICADORES={"DEC":"INF-ENE-01","FEC":"INF-ENE-02"}

def parse_decimal(value:str)->float|None:
    value=value.strip().replace(".","").replace(",",".")
    return None if not value else float(value)

def ipf(support:set[tuple[str,str]],row_margins:dict[str,float],column_margins:dict[str,float],*,tolerance=1e-8,max_iterations=10_000):
    issues=[]
    if abs(sum(row_margins.values())-sum(column_margins.values()))>tolerance:
        return {},[f"margens incompatíveis: municipios={sum(row_margins.values()):.6f}; conjuntos={sum(column_margins.values()):.6f}"]
    cells={edge:1. for edge in support}
    if any(not any(m==r for m,_ in support) for r in row_margins) or any(not any(c==col for _,c in support) for col in column_margins): return {},["margem positiva sem célula na matriz de suporte"]
    for _ in range(max_iterations):
        for r,target in row_margins.items():
            keys=[k for k in cells if k[0]==r]; total=sum(cells[k] for k in keys)
            for k in keys: cells[k]*=target/total
        for c,target in column_margins.items():
            keys=[k for k in cells if k[1]==c]; total=sum(cells[k] for k in keys)
            for k in keys: cells[k]*=target/total
        errors=[abs(sum(v for (r,_),v in cells.items() if r==key)-target) for key,target in row_margins.items()]+[abs(sum(v for (_,c),v in cells.items() if c==key)-target) for key,target in column_margins.items()]
        if max(errors)<=tolerance:return cells,issues
    return {},[f"IPF não convergiu em {max_iterations} iterações"]

def territorialize(municipalities:Iterable[str],relations:Iterable[dict[str,str]],set_values:dict[str,dict[str,float]],weights:dict[tuple[str,str],float]|None=None,*,allow_fallback=True)->list[dict[str,object]]:
    links=defaultdict(set)
    for row in relations:links[row["municipio_id"]].add(row["conjunto_id"])
    output=[]
    for municipality in municipalities:
      sets=sorted(links.get(municipality,set()))
      for source,indicator in INDICADORES.items():
        available=[(s,set_values.get(s,{}).get(source)) for s in sets]; available=[x for x in available if x[1] is not None]
        value=None;level=None;approx=False;used={}
        if len(sets)==1 and len(available)==1:value,level=available[0][1],1
        elif available and len(available)==len(sets) and weights and all(math.isfinite(weights.get((municipality,s),0)) and weights.get((municipality,s),0)>0 for s,_ in available):
            used={s:weights[(municipality,s)] for s,_ in available}; denominator=sum(used.values());value=sum(v*used[s] for s,v in available)/denominator;level=2
        elif allow_fallback and available and len(available)==len(sets):value=sum(v for _,v in available)/len(available);level=4;approx=True
        if value is not None:value=round(value,6)
        output.append({"municipio_id":municipality,"indicador_id":indicator,"valor_bruto":value,"periodo_referencia":PERIODO,"flag_qualidade":"ausente" if value is None else ("territorializacao_aproximada" if approx else "observado"),"metodo_territorializacao":None if level is None else f"nivel_{level}","territorializacao_aproximada":approx,"pesos_uc":"|".join(f"{s}:{used[s]:g}" for s in sorted(used))})
    return output

def read_annual_set_values(path:Path,year=PERIODO):
    totals=defaultdict(float);seen=set();periods=defaultdict(set)
    with path.open(encoding="utf-8-sig") as stream:
      for row in csv.DictReader(stream,delimiter=";"):
        indicator=row["SigIndicador"].strip();period=row["NumPeriodoIndice"].strip()
        if row["AnoIndice"]!=year or indicator not in INDICADORES:continue
        key=(row["IdeConjUndConsumidoras"],indicator,period)
        if key in seen:raise ValueError(f"duplicidade ANEEL: {key}")
        seen.add(key);value=parse_decimal(row["VlrIndiceEnviado"])
        if value is not None:totals[key[:2]]+=value;periods[key[:2]].add(period)
    complete={k:v for k,v in totals.items() if periods[k]=={str(i) for i in range(1,13)}}
    result=defaultdict(dict)
    for (set_id,indicator),value in complete.items():result[set_id][indicator]=value
    return dict(result)

def read_relations(path:Path):
    for encoding in ("utf-8-sig","latin1"):
      try:
        with path.open(encoding=encoding) as stream:return [{"municipio_id":r["CodMunicipio"],"conjunto_id":r["IdeConjUnidConsumidoras"]} for r in csv.DictReader(stream,delimiter=";")]
      except UnicodeDecodeError:pass
    raise ValueError("codificação do IndQual Município não reconhecida")

def aggregate_bdgd_rows(layers:Iterable[tuple[str,Iterable[dict[str,object]]]]):
    """Agrega UCs ativas de camadas de tensão disjuntas no peso município×conjunto."""
    weights=Counter();sources=[]
    for layer,rows in layers:
      count=0
      for row in rows:
        municipality=row.get("MUN");set_id=row.get("CONJ");status=row.get("SIT_ATIV")
        if municipality and set_id is not None and str(set_id).strip() and str(status).strip()=="AT":
          try: normalized_set=str(int(set_id))
          except (TypeError,ValueError):continue
          weights[(str(municipality),normalized_set)]+=1;count+=1
      sources.append({"tabela":layer,"registros_ativos":count,"campos":["MUN","CONJ","SIT_ATIV"]})
    return dict(weights),sources

def read_bdgd_weights(paths:Iterable[Path]):
    """Conta UCs ativas nas tabelas disjuntas por tensão UCBT/UCMT/UCAT."""
    try:from pyogrio.raw import read
    except ImportError as exc:raise RuntimeError("pyogrio é necessário para ler File Geodatabase BDGD") from exc
    import zipfile
    weights=Counter();sources=[]
    for path in paths:
      if not path.exists():continue
      root=zipfile.ZipFile(path).namelist()[0].rstrip("/");dataset=f"/vsizip/{path.resolve()}/{root}"
      layer_rows=[]
      for layer in ("UCBT_tab","UCMT_tab","UCAT_tab"):
        meta,_,_,arrays=read(dataset,layer=layer,read_geometry=False,columns=["MUN","CONJ","SIT_ATIV"]);columns=dict(zip(meta["fields"],arrays))
        layer_rows.append((layer,({"MUN":m,"CONJ":c,"SIT_ATIV":s} for m,c,s in zip(columns["MUN"],columns["CONJ"],columns["SIT_ATIV"]))))
      found,details=aggregate_bdgd_rows(layer_rows);weights.update(found)
      for detail in details:detail["arquivo"]=path.name;sources.append(detail)
    return dict(weights),sources

def audit(rows:list[dict[str,object]]):
    by_indicator={indicator:{"metodos":Counter(),"ausentes":[]} for indicator in INDICADORES.values()}
    municipality=defaultdict(set)
    for row in rows:
      indicator=row["indicador_id"]
      if row["valor_bruto"] is None:by_indicator[indicator]["ausentes"].append(row["municipio_id"]);municipality[row["municipio_id"]].add("missing_"+indicator)
      else:by_indicator[indicator]["metodos"][row["metodo_territorializacao"]]+=1;municipality[row["municipio_id"]].add(row["metodo_territorializacao"])
    both=sum(1 for x in municipality.values() if {"missing_INF-ENE-01","missing_INF-ENE-02"}<=x)
    return {"por_indicador":{k:{"metodos":dict(v["metodos"]),"n_ausente":len(v["ausentes"]),"municipios_ausentes":v["ausentes"]} for k,v in by_indicator.items()},"missing_ambos":both}

def write_csv(rows,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as stream:w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
