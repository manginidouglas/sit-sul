"""Pontuação/publicação offline da edição; entradas ausentes nunca são inventadas."""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path
import yaml
from .quality import indicator_quality
from .scoring import DegenerateIndicator,axis_score,minmax,overall,winsorize
from .validate import validate_municipal_keys,validate_scores
DISCLAIMER=("Esta é uma demonstração experimental do Sistema de Inteligência Territorial (SIT), construída com os eixos Infraestrutura e Conectividade e Mercado. O SIT completo prevê seis eixos. Alguns parâmetros desta demonstração foram fixados provisoriamente para testar o funcionamento do sistema de ponta a ponta e não representam decisões metodológicas definitivas.")

def population_group(value):
    if value in (None,""): return "nao_informado"
    n=float(value)
    return "ate_20_mil" if n<20000 else "20_a_100_mil" if n<100000 else "100_a_500_mil" if n<500000 else "500_mil_ou_mais"

def run(config_path:Path,municipalities_path:Path,indicators_path:Path,output_dir:Path,canonical_path:Path|None=None):
    config=yaml.safe_load(config_path.read_text(encoding="utf-8")); canonical_path=canonical_path or municipalities_path
    def read(path):
        with path.open(encoding="utf-8") as f:return list(csv.DictReader(f))
    municipalities,canonical=read(municipalities_path),read(canonical_path);validate_municipal_keys(municipalities,canonical)
    by_id={r["municipio_id"]:dict(r) for r in municipalities}
    for r in by_id.values():
        r.setdefault("populacao","");r["grupo_porte"]=population_group(r.get("populacao"));r["municipio"]=r.get("municipio_nome","");r["UF"]=r.get("uf_sigla","")
    observations=read(indicators_path);seen=set();values=defaultdict(dict);metadata={}
    for row in observations:
        key=(row["municipio_id"],row["indicador_id"])
        if key in seen:raise ValueError(f"observação duplicada: {key}")
        seen.add(key)
        if row["municipio_id"] not in by_id:continue
        raw=row.get("valor_bruto","").strip();values[row["indicador_id"]][row["municipio_id"]]=None if raw=="" else float(raw);metadata[key]=row
        if row.get("populacao"):
            by_id[row["municipio_id"]]["populacao"]=row["populacao"];by_id[row["municipio_id"]]["grupo_porte"]=population_group(row["populacao"])
    ids=sorted(by_id);scores=defaultdict(dict);quality=[];params={};rules=config["indicadores"]
    for indicator,rule in rules.items():
        raw=[values[indicator].get(mid) for mid in ids];valid=[x for x in raw if x is not None];treated=list(raw);lo=hi=None;winflags=[False]*len(ids)
        if valid and rule.get("peso",0)>0 and not rule.get("limite_natural",False):treated,lo,hi,winflags=winsorize(raw,*config["parametros"]["winsorizacao"])
        transformed=[None if x is None else math.log1p(x) for x in treated] if indicator in config["parametros"]["log1p"] else list(treated)
        indicator_scores=[None]*len(ids);minimum=maximum=None
        if valid and rule.get("peso",0)>0:
            try:indicator_scores,minimum,maximum=minmax(transformed,rule["direcao"])
            except (ValueError,DegenerateIndicator):pass
        validate_scores(indicator_scores);params[indicator]={"p1":lo,"p99":hi,"min":minimum,"max":maximum,"direcao":rule["direcao"]}
        quality.append(indicator_quality(indicator,ids,raw,treated,winflags,metadata,by_id))
        for i,mid in enumerate(ids):
            scores[mid][indicator]=indicator_scores[i];out=by_id[mid];meta=metadata.get((mid,indicator),{})
            flag=meta.get("flag_qualidade") or ("ausente" if raw[i] is None else "observado")
            out.update({f"{indicator}_valor_bruto":raw[i],f"{indicator}_valor_tratado":treated[i],f"{indicator}_valor_transformado":transformed[i],f"{indicator}_score":indicator_scores[i],f"{indicator}_periodo":meta.get("periodo_referencia",""),f"{indicator}_flag_qualidade":flag,f"{indicator}_winsorizado":winflags[i]})
    core={k:v for k,v in rules.items() if v.get("peso",0)>0};threshold=config["parametros"]["cobertura_minima_eixo"]
    iw={k:float(v["peso"]) for k,v in core.items() if v["eixo"]=="infra"};mw={k:float(v["peso"]) for k,v in core.items() if v["eixo"]=="mercado"}
    blocks=defaultdict(dict)
    for k,v in core.items():
        if v["eixo"]=="infra":blocks[v["bloco"]][k]=float(v["peso"])
    for mid in ids:
        for block,bw in blocks.items():by_id[mid][f"bloco_{block}"]=axis_score(scores[mid],bw,0)[0]
        infra,ci=axis_score(scores[mid],iw,threshold);market,cm=axis_score(scores[mid],mw,threshold)
        by_id[mid].update(nota_infra=infra,nota_mercado=market,cobertura_infra=ci,cobertura_mercado=cm,nota_geral=overall(infra,market,config["parametros"]["pesos_eixos"]),disclaimer=DISCLAIMER)
    ranked=sorted(by_id.values(),key=lambda r:(r["nota_geral"] is None,-(r["nota_geral"] or 0),r["municipio_id"]));ufrank=defaultdict(int);porterank=defaultdict(int);rank=0
    for r in ranked:
        if r["nota_geral"] is not None:
            rank+=1;ufrank[r["uf_sigla"]]+=1;porterank[r["grupo_porte"]]+=1;r.update(ranking_sul=rank,ranking_uf=ufrank[r["uf_sigla"]],ranking_porte=porterank[r["grupo_porte"]])
        else:r.update(ranking_sul=None,ranking_uf=None,ranking_porte=None)
    output_dir.mkdir(parents=True,exist_ok=True);fields=list(ranked[0])
    with (output_dir/"municipios.csv").open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranked)
    for name,obj in (("parametros-score.json",params),("qualidade.json",quality)):(output_dir/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return ranked

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--config",type=Path,default=Path("config/edicoes/mvp-demo-2026.yml"));p.add_argument("--municipios",type=Path,default=Path("data/processed/2026/municipios.csv"));p.add_argument("--canonical",type=Path);p.add_argument("--indicadores",type=Path,required=True);p.add_argument("--output",type=Path,default=Path("data/output/mvp-demo-2026"));a=p.parse_args(argv);run(a.config,a.municipios,a.indicadores,a.output,a.canonical);return 0
if __name__=="__main__":raise SystemExit(main())
