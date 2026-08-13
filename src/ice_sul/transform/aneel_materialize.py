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

def qa(rows,municipalities,relations,weights,bdgd_sources,set_values):
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
    return report

def materialize(raw_dir:Path,canonical_path:Path,interim_dir:Path,report_dir:Path,bdgd_paths=()):
    municipalities=canonical(canonical_path);ids=[r["municipio_id"] for r in municipalities];idset=set(ids)
    with tempfile.TemporaryDirectory() as tmp:values=read_annual_set_values(extract_continuity(raw_dir/"indicadores-continuidade-2020-2029.zip",Path(tmp)/"continuidade.csv"))
    raw_relations=read_relations(raw_dir/"indqual-municipio.csv")
    relations=[r for r in raw_relations if r["municipio_id"] in idset and r["conjunto_id"] in values]
    weights,sources=read_bdgd_weights(bdgd_paths) if bdgd_paths else ({},[]);weights={k:v for k,v in weights.items() if k[0] in idset}
    rows=territorialize(ids,relations,values,weights);validate_output(rows,ids)
    interim_dir.mkdir(parents=True,exist_ok=True);write_csv(rows,interim_dir/"indicadores_municipais_2025.csv")
    report=qa(rows,municipalities,relations,weights,sources,values);(interim_dir/"auditoria.json").write_text(json.dumps(report["auditoria"],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report_dir.mkdir(parents=True,exist_ok=True);(report_dir/"qa.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("--raw-dir",type=Path,default=Path("data/raw/aneel"));parser.add_argument("--canonical",type=Path,default=Path("data/processed/2026/municipios.csv"));parser.add_argument("--interim-dir",type=Path,default=Path("data/interim/aneel"));parser.add_argument("--report-dir",type=Path,default=Path("reports/quality/mvp-demo-2026/aneel"));parser.add_argument("--bdgd",type=Path,nargs="*",default=[])
    args=parser.parse_args(argv);report=materialize(args.raw_dir,args.canonical,args.interim_dir,args.report_dir,args.bdgd);print(json.dumps(report["auditoria"],ensure_ascii=False))
if __name__=="__main__":main()
