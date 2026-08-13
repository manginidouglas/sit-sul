"""CLI reproduzível: raws oficiais ANEEL -> indicadores e QA municipal."""
from __future__ import annotations
import argparse,csv,json,math,shutil,statistics,tempfile,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from .aneel import INDICADORES,audit,read_annual_set_values,read_bdgd_weights,read_relations,territorialize,write_csv

EXPECTED=1191
def canonical(path:Path):
    with path.open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
    ids=[r["municipio_id"] for r in rows]
    if len(rows)!=EXPECTED or len(set(ids))!=EXPECTED or any(len(x)!=7 or not x.isdigit() for x in ids):raise ValueError("universo canônico inválido: esperado 1.191 IDs únicos de sete dígitos")
    return rows

def extract_continuity(archive:Path,destination:Path):
    if not zipfile.is_zipfile(archive):raise ValueError(f"ZIP de continuidade inválido: {archive}")
    with zipfile.ZipFile(archive) as z:
      candidates=[x for x in z.namelist() if x.endswith("indicadores-continuidade-coletivos-2020-2029.csv")]
      if len(candidates)!=1:raise ValueError(f"ZIP deve conter exatamente um CSV de continuidade; encontrados {candidates}")
      destination.parent.mkdir(parents=True,exist_ok=True)
      with z.open(candidates[0]) as source,destination.open("wb") as target:shutil.copyfileobj(source,target)
    return destination

def read_set_agents(path:Path):
    agents={}
    with path.open(encoding="utf-8-sig") as stream:
      for row in csv.DictReader(stream,delimiter=";"):
        if row["AnoIndice"]=="2025" and row["SigIndicador"].strip() in ("DEC","FEC"):
          agents[row["IdeConjUndConsumidoras"]]={"distribuidora":row.get("SigAgente","").strip() or "Não identificado","conjunto_nome":row.get("DscConjUndConsumidoras","").strip()}
    return agents

def validate_output(rows,ids):
    keys=[(r["municipio_id"],r["indicador_id"]) for r in rows];expected={(m,i) for m in ids for i in INDICADORES.values()}
    if len(rows)!=2382 or set(keys)!=expected or len(keys)!=len(set(keys)):raise ValueError("output deve ter exatamente DEC e FEC para cada município canônico")

def percentile(values,p):
    values=sorted(values);position=(len(values)-1)*p;lower=int(position);upper=min(lower+1,len(values)-1);return values[lower]+(values[upper]-values[lower])*(position-lower)
def stats(values,total):
    if not values:return {"n_observado":0,"n_ausente":total}
    return {"n_observado":len(values),"n_ausente":total-len(values),"minimo":min(values),"p1":percentile(values,.01),"p5":percentile(values,.05),"mediana":statistics.median(values),"p95":percentile(values,.95),"p99":percentile(values,.99),"maximo":max(values),"media":statistics.mean(values)}
def ranks(values):
    order=sorted(range(len(values)),key=values.__getitem__);result=[0.]*len(values);i=0
    while i<len(order):
      j=i+1
      while j<len(order) and values[order[j]]==values[order[i]]:j+=1
      rank=(i+j-1)/2+1
      for k in order[i:j]:result[k]=rank
      i=j
    return result
def correlation(a,b):
    ra,rb=ranks(a),ranks(b);ma,mb=statistics.mean(ra),statistics.mean(rb);den=math.sqrt(sum((x-ma)**2 for x in ra)*sum((y-mb)**2 for y in rb));return sum((x-ma)*(y-mb) for x,y in zip(ra,rb))/den if den else None

def fallback_diagnostics(rows,municipalities,relations,weights,set_agents,bdgd_paths):
    metadata={r["municipio_id"]:r for r in municipalities};links=defaultdict(set)
    for r in relations:links[r["municipio_id"]].add(r["conjunto_id"])
    aliases={"copel":"COPEL-DIS","celesc":"CELESC","rge":"RGE SUL","ceee":"CEEE-D","certel":"CERTEL ENERGIA","cerfox":"CERFOX","creluz":"CRELUZ-D","celetro":"CELETRO","cermissoes":"CERMISSÕES","ceriluz":"CERILUZ","certaja":"CERTAJA","cooperluz":"COOPERLUZ","eletrocar":"ELETROCAR","coprel":"COPREL"}
    investigated={aliases.get(p.stem.lower(),p.stem.upper()) for p in bdgd_paths};all_weighted_sets={s for _,s in weights};output=[]
    level4={r["municipio_id"] for r in rows if r["indicador_id"]=="INF-ENE-01" and r["metodo_territorializacao"]=="nivel_4"}
    for municipality in sorted(level4):
      needed=sorted(links[municipality],key=int);present=[s for s in needed if weights.get((municipality,s),0)>0];missing=[s for s in needed if s not in present];agents=sorted({set_agents.get(s,{}).get("distribuidora","Não identificado") for s in missing})
      if any(a=="Não identificado" or a=="Não Informado" for a in agents):reason="conjunto não identificado"
      elif any(a not in investigated for a in agents):reason="conjunto provavelmente pertence a distribuidora local"
      elif any(s in all_weighted_sets for s in missing):reason="conjunto sem peso na BDGD 2024 do agente principal"
      else:reason="possível mudança de conjunto 2024→2025"
      m=metadata[municipality];output.append({"municipio_id":municipality,"municipio_nome":m["municipio_nome"],"uf_sigla":m["uf_sigla"],"conjuntos_necessarios":"|".join(needed),"conjuntos_com_peso":"|".join(present),"conjuntos_sem_peso":"|".join(missing),"n_conjuntos_necessarios":len(needed),"n_conjuntos_com_peso":len(present),"motivo_nivel4":reason,"distribuidora_provavel_do_conjunto_sem_peso":"|".join(agents),"bdgd_disponivel":all(a not in {"Não identificado","Não Informado"} for a in agents),"bdgd_investigada":all(a in investigated for a in agents)})
    return output

def qa(rows,municipalities,relations,weights,bdgd_sources,set_values,set_agents,bdgd_paths,report_dir):
    metadata={r["municipio_id"]:r for r in municipalities};links=defaultdict(set)
    for r in relations:links[r["municipio_id"]].add(r["conjunto_id"])
    report={"auditoria":audit(rows),"estatisticas":{"sul":{},"por_uf":{},"por_metodo":{}},"bdgd":{"fontes":bdgd_sources,"n_pesos_municipio_conjunto":len(weights)},"ausentes":[],"sanity_checks":[],"extremos":{},"validacoes":{}}
    dec_rows=[r for r in rows if r["indicador_id"]=="INF-ENE-01"]
    report["territorializacao"]={method:{"municipios":sum(r["metodo_territorializacao"]==method for r in dec_rows),"percentual":round(100*sum(r["metodo_territorializacao"]==method for r in dec_rows)/EXPECTED,4)} for method in ("nivel_1","nivel_2","nivel_3","nivel_4")}
    report["territorializacao"]["ausente"]={"municipios":sum(r["valor_bruto"] is None for r in dec_rows),"percentual":round(100*sum(r["valor_bruto"] is None for r in dec_rows)/EXPECTED,4)}
    for indicator in INDICADORES.values():
      selected=[r for r in rows if r["indicador_id"]==indicator];report["estatisticas"]["sul"][indicator]=stats([r["valor_bruto"] for r in selected if r["valor_bruto"] is not None],EXPECTED)
      report["estatisticas"]["por_uf"][indicator]={uf:stats([r["valor_bruto"] for r in selected if metadata[r["municipio_id"]]["uf_sigla"]==uf and r["valor_bruto"] is not None],sum(metadata[r["municipio_id"]]["uf_sigla"]==uf for r in selected)) for uf in ("PR","SC","RS")}
      report["estatisticas"]["por_metodo"][indicator]={method:stats([r["valor_bruto"] for r in selected if r["metodo_territorializacao"]==method and r["valor_bruto"] is not None],sum(r["metodo_territorializacao"]==method for r in selected)) for method in ("nivel_1","nivel_2","nivel_3","nivel_4")}
      observed=[r for r in selected if r["valor_bruto"] is not None];report["extremos"][indicator]={"bottom_10":sorted(observed,key=lambda r:r["valor_bruto"])[:10],"top_10":sorted(observed,key=lambda r:r["valor_bruto"],reverse=True)[:10]}
    for r in rows:
      if r["valor_bruto"] is None:
       m=metadata[r["municipio_id"]];report["ausentes"].append({"municipio_id":r["municipio_id"],"municipio_nome":m["municipio_nome"],"uf_sigla":m["uf_sigla"],"indicador_id":r["indicador_id"],"motivo":"sem relação ativa com valor anual completo para o indicador","conjuntos_relacionados":sorted(links[r["municipio_id"]])})
    names=("Curitiba","Florianópolis","Porto Alegre","Abatiá","Abdon Batista","Aceguá")
    for name in names:
      m=next(x for x in municipalities if x["municipio_nome"]==name);rr=[x for x in rows if x["municipio_id"]==m["municipio_id"]]
      report["sanity_checks"].append({"municipio_id":m["municipio_id"],"municipio_nome":name,"uf_sigla":m["uf_sigla"],"conjuntos":sorted(links[m["municipio_id"]]),"pesos":{s:weights.get((m["municipio_id"],s)) for s in sorted(links[m["municipio_id"]]) if (m["municipio_id"],s) in weights},"resultados":rr})
    values=[r["valor_bruto"] for r in rows if r["valor_bruto"] is not None];report["validacoes"]={"linhas":len(rows),"municipios":len({r["municipio_id"] for r in rows}),"negativos":sum(v<0 for v in values),"nao_finitos":sum(not math.isfinite(v) for v in values),"zeros":sum(v==0 for v in values)}
    simple=territorialize([m["municipio_id"] for m in municipalities],relations,set_values,{})
    simple_by_key={(r["municipio_id"],r["indicador_id"]):r for r in simple}
    comparison={}
    for indicator in INDICADORES.values():
      pairs=[]
      for r in rows:
       if r["indicador_id"]==indicator and r["metodo_territorializacao"]=="nivel_2":
        other=simple_by_key[(r["municipio_id"],indicator)];pairs.append((r,other,abs(r["valor_bruto"]-other["valor_bruto"])))
      weighted=[x[0]["valor_bruto"] for x in pairs];unweighted=[x[1]["valor_bruto"] for x in pairs];differences=[x[2] for x in pairs]
      comparison[indicator]={"municipios_afetados":len(pairs),"spearman":correlation(weighted,unweighted) if pairs else None,"diferenca_absoluta_mediana":statistics.median(differences) if pairs else None,"diferenca_absoluta_p95":percentile(differences,.95) if pairs else None,"diferenca_maxima":max(differences) if pairs else None,"maiores_mudancas":[{"municipio_id":x[0]["municipio_id"],"municipio_nome":metadata[x[0]["municipio_id"]]["municipio_nome"],"uf_sigla":metadata[x[0]["municipio_id"]]["uf_sigla"],"ponderado":x[0]["valor_bruto"],"media_simples":x[1]["valor_bruto"],"diferenca_absoluta":x[2]} for x in sorted(pairs,key=lambda x:x[2],reverse=True)[:10]],"por_uf":{uf:{"n":len(d),"diferenca_absoluta_mediana":statistics.median(d) if d else None,"diferenca_absoluta_p95":percentile(d,.95) if d else None} for uf in ("PR","SC","RS") for d in [[x[2] for x in pairs if metadata[x[0]["municipio_id"]]["uf_sigla"]==uf]]}}
    report["comparacao_bdgd_media_simples"]=comparison
    diagnostics=fallback_diagnostics(rows,municipalities,relations,weights,set_agents,bdgd_paths)
    diagnostic_path=report_dir/"fallback_nivel4_diagnostico.csv"
    if diagnostics:write_csv(diagnostics,diagnostic_path)
    else:diagnostic_path.write_text("municipio_id,municipio_nome,uf_sigla,conjuntos_necessarios,conjuntos_com_peso,conjuntos_sem_peso,n_conjuntos_necessarios,n_conjuntos_com_peso,motivo_nivel4,distribuidora_provavel_do_conjunto_sem_peso,bdgd_disponivel,bdgd_investigada\n",encoding="utf-8")
    report["fallback_nivel4"]={"n_municipios":len(diagnostics),"n_conjuntos_sem_peso":len({s for d in diagnostics for s in d["conjuntos_sem_peso"].split("|") if s}),"municipios_por_motivo":dict(Counter(d["motivo_nivel4"] for d in diagnostics))}
    agent_sets=defaultdict(set);agent_municipalities=defaultdict(set)
    for d in diagnostics:
      for s in d["conjuntos_sem_peso"].split("|"):
       if s:agent=set_agents.get(s,{}).get("distribuidora","Não identificado");agent_sets[agent].add(s);agent_municipalities[agent].add(d["municipio_id"])
    aliases={"copel":"COPEL-DIS","celesc":"CELESC","rge":"RGE SUL","ceee":"CEEE-D","certel":"CERTEL ENERGIA","cerfox":"CERFOX","creluz":"CRELUZ-D","celetro":"CELETRO","cermissoes":"CERMISSÕES","ceriluz":"CERILUZ","certaja":"CERTAJA","cooperluz":"COOPERLUZ","eletrocar":"ELETROCAR","coprel":"COPREL"}
    investigated={aliases.get(Path(d["arquivo"]).stem.lower(),Path(d["arquivo"]).stem.upper()) for d in bdgd_sources}
    report["fallback_por_distribuidora"]=[{"distribuidora":a,"n_conjuntos_sem_peso":len(agent_sets[a]),"n_municipios_nivel4_afetados":len(agent_municipalities[a]),"bdgd_disponivel":a not in {"Não identificado","Não Informado"},"bdgd_investigada":a in investigated,"vintage":"2024-12-31 (Coprel: 2023-12-31)","prioridade_de_download":i+1} for i,a in enumerate(sorted(agent_sets,key=lambda a:len(agent_municipalities[a]),reverse=True))]
    weighted_sets={s for _,s in weights};required={r["conjunto_id"] for r in relations};missing_sets=required-weighted_sets
    report["compatibilidade_temporal"]={"vintage_bdgd":"2024-12-31 (Coprel: 2023-12-31)","conjuntos_2025_necessarios":len(required),"conjuntos_2025_ausentes_nas_bdgd":len(missing_sets),"municipios_multiconjunto_impedidos_por_ausencia_de_conjunto":sum(any(s in missing_sets for s in d["conjuntos_sem_peso"].split("|")) for d in diagnostics),"equivalencias_inferidas":0,"nota":"IDs não foram ligados por nome; ausências são compatíveis com criação, renomeação ou reorganização entre vintages, mas só relação oficial permitiria afirmar equivalência."}
    report["diagnosticos_capitais"]={name:next((d for d in diagnostics if d["municipio_nome"]==name),None) for name in ("Curitiba","Porto Alegre")}
    return report

def materialize(raw_dir:Path,canonical_path:Path,interim_dir:Path,report_dir:Path,bdgd_paths=()):
    municipalities=canonical(canonical_path);ids=[r["municipio_id"] for r in municipalities];idset=set(ids)
    with tempfile.TemporaryDirectory() as tmp:
      continuity=extract_continuity(raw_dir/"indicadores-continuidade-2020-2029.zip",Path(tmp)/"continuidade.csv");values=read_annual_set_values(continuity);set_agents=read_set_agents(continuity)
    raw_relations=read_relations(raw_dir/"indqual-municipio.csv")
    relations=[r for r in raw_relations if r["municipio_id"] in idset and r["conjunto_id"] in values]
    weights,sources=read_bdgd_weights(bdgd_paths) if bdgd_paths else ({},[]);weights={k:v for k,v in weights.items() if k[0] in idset}
    rows=territorialize(ids,relations,values,weights);validate_output(rows,ids)
    interim_dir.mkdir(parents=True,exist_ok=True);write_csv(rows,interim_dir/"indicadores_municipais_2025.csv")
    report_dir.mkdir(parents=True,exist_ok=True);report=qa(rows,municipalities,relations,weights,sources,values,set_agents,bdgd_paths,report_dir);(interim_dir/"auditoria.json").write_text(json.dumps(report["auditoria"],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (report_dir/"qa.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("--raw-dir",type=Path,default=Path("data/raw/aneel"));parser.add_argument("--canonical",type=Path,default=Path("data/processed/2026/municipios.csv"));parser.add_argument("--interim-dir",type=Path,default=Path("data/interim/aneel"));parser.add_argument("--report-dir",type=Path,default=Path("reports/quality/mvp-demo-2026/aneel"));parser.add_argument("--bdgd",type=Path,nargs="*",default=[])
    args=parser.parse_args(argv);report=materialize(args.raw_dir,args.canonical,args.interim_dir,args.report_dir,args.bdgd);print(json.dumps(report["auditoria"],ensure_ascii=False))
if __name__=="__main__":main()
