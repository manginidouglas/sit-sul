import csv,yaml
from pathlib import Path
from ice_sul.mvp.pipeline import run
from ice_sul.mvp.robustness import compare_rankings
from ice_sul.mvp.validate import validate_municipal_keys

def write_csv(path,rows):
    fields=list(rows[0]);
    with path.open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def config(tmp_path,coverage=.8,axis=(.5,.5)):
    cfg=yaml.safe_load(Path('config/edicoes/mvp-demo-2026.yml').read_text());cfg['parametros']['cobertura_minima_eixo']=coverage;cfg['parametros']['pesos_eixos']={'infra':axis[0],'mercado':axis[1]};p=tmp_path/'c.yml';p.write_text(yaml.safe_dump(cfg));return p,cfg

def test_partial_source_missing_diagnostics_blocks_and_config(tmp_path):
    mun=[{'municipio_id':'4106902','municipio_nome':'Curitiba','uf_sigla':'PR','populacao':'1000000'},{'municipio_id':'4205407','municipio_nome':'Florianópolis','uf_sigla':'SC','populacao':'500000'}];mp=tmp_path/'m.csv';write_csv(mp,mun);cp,cfg=config(tmp_path,coverage=.81)
    rows=[]
    for n,m in enumerate(mun):
      for iid,r in cfg['indicadores'].items():
       value='' if iid=='INF-LOG-04' else ('.4' if iid=='MER-DIAG-01' else str(n+1))
       rows.append({'municipio_id':m['municipio_id'],'indicador_id':iid,'valor_bruto':value,'periodo_referencia':'2025','flag_qualidade':'ausente' if value=='' else 'observado'})
    ip=tmp_path/'i.csv';write_csv(ip,rows);out=tmp_path/'out';result=run(cp,mp,ip,out)
    assert result[0]['INF-LOG-04_score'] is None and result[0]['INF-LOG-04_flag_qualidade']=='ausente'
    assert result[0]['MER-DIAG-01_valor_bruto']==.4 and result[0]['MER-DIAG-01_score'] is None
    assert 'bloco_digital' in result[0] and result[0]['grupo_porte']=='500_mil_ou_mais'
    assert next(x for x in __import__('json').loads((out/'qualidade.json').read_text()) if x['indicador_id']=='INF-LOG-04')['status']=='indisponivel'
    cp2,_=config(tmp_path,coverage=.79,axis=(.9,.1));result2=run(cp2,mp,ip,tmp_path/'out2')
    assert result[0]['nota_geral'] is None and result2[0]['nota_geral'] is not None

def test_noncanonical_valid_ids_rejected():
    canonical=[{'municipio_id':'4106902','municipio_nome':'Curitiba','uf_sigla':'PR'}]
    try:validate_municipal_keys([{'municipio_id':'9999999','municipio_nome':'X','uf_sigla':'PR'}],canonical)
    except ValueError:pass
    else:raise AssertionError('universo sintaticamente válido mas não canônico aceito')

def test_robustness_metrics():
    result=compare_rankings({'a':1,'b':2,'c':3},{'a':3,'b':2,'c':1})
    assert result['spearman']==-1 and result['maior_mudanca']==2 and result['mais_sensiveis'][0][0]=='a'
