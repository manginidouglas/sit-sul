#!/usr/bin/env python3
"""Materialização determinística e transacional dos artefatos ANAC da Onda 1."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from ice_sul.extract.anac import AnacCollector, sha256_stream
from ice_sul.transform.anac import (
    OUTPUT_FIELDS, assess_publication_integrity, build_airport_scores_streaming, publish_atomic,
    read_aerodromes, read_siros,
)
from ice_sul.transform.anac_sensitivity import compare_access_scenarios

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data/raw/anac"; OUT=ROOT/"data/interim/anac"; REPORT=ROOT/"reports/quality/mvp-demo-2026/anac"
MISSING_FIELDS=("codigo","nome","uf","pais","meses_com_servico","meses_lista","decolagens","destinos_distintos","atingiria_limiar_se_ligada","motivo_ausencia","fontes_oficiais_investigadas","conclusao")
EXTERNAL_FIELDS=("codigo","nome","pais","decolagens","meses_com_servico","meses_lista")
ALIAS_FIELDS=("alias","aeroporto_id","tipo","fonte")


def count_resource(path: Path) -> tuple[int,list[str]]:
    from ice_sul.transform.anac import _open_text
    with _open_text(path) as stream:
        first=stream.readline().strip(); reader=csv.DictReader(stream,delimiter=";")
        return sum(1 for row in reader if any(row.values())), list(reader.fieldnames or [])


def _osrm_evidence(report: Path) -> tuple[dict, list[dict]]:
    previous=ROOT/"tests/fixtures/anac/osrm_response.json"
    raw=json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else {"code":"not_collected"}
    response=json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    evidence={"status":"exploratorio_nao_reproduzivel_sem_snapshot","snapshot_rede":None,"perfil":"driving","servidor":"https://router.project-osrm.org","ordem_coordenadas":"longitude,latitude","data_hora_utc":"2026-08-15T13:00:00+00:00","municipios":[{"municipio_id":"4106902","nome":"Curitiba","coordenadas":[-49.267944,-25.413486]},{"municipio_id":"4113205","nome":"Lapa","coordenadas":[-49.716,-25.769]}],"aeroportos":[{"aeroporto_id":"SBCT","coordenadas":[-49.176673,-25.531876]},{"aeroporto_id":"SBJV","coordenadas":[-48.796477,-26.222123]},{"aeroporto_id":"SBPA","coordenadas":[-51.170625,-29.997527]}],"parametros":{"sources":"0;1","destinations":"2;3;4","annotations":"duration,distance"},"resposta":raw,"sha256_resposta":hashlib.sha256(response).hexdigest(),"snapping":{"origens_metros":[21.075,0],"destinos_metros":[60.807,279.035,316.714]}}
    routes=[]
    if raw.get("durations"):
        for mi,municipio in enumerate(evidence["municipios"]):
            for ai,airport in enumerate(evidence["aeroportos"]): routes.append({"municipio_id":municipio["municipio_id"],"aeroporto_id":airport["aeroporto_id"],"tempo_minutos":raw["durations"][mi][ai]/60})
    return evidence,routes


def materialize(raw: Path=RAW,out: Path=OUT,report: Path=REPORT, *, revalidation_utc: str | None=None) -> dict:
    raw=raw.resolve(); out=out.resolve(); report=report.resolve()
    revalidation_utc=revalidation_utc or datetime.now(UTC).isoformat()
    collector=AnacCollector(movements_path=raw/"Dados_Estatisticos.csv",public_path=raw/"cadastro-aerodromos-publicos.csv",private_path=raw/"cadastro-aerodromos-privados.csv",heliports_path=raw/"helipontos.csv",helidecks_path=raw/"helidecks.csv",siros_path=raw/"aerodromos-siros.csv",frozen_manifest_path=report/"frozen-snapshot.json",revalidation_utc=revalidation_utc)
    result=collector.collect()
    if result.status != "success": raise RuntimeError(f"coleta não validada: {result.status}: {result.errors}")
    public=read_aerodromes(collector.public_path,tipo_cadastro="publico")
    private=read_aerodromes(collector.private_path,tipo_cadastro="privativo")
    siros=read_siros(collector.siros_path)
    catalogue=public+private
    rows,qa=build_airport_scores_streaming(catalogue,collector.movements_path)
    for entry in result.manifest_entries:
        entry["arquivo"]=f"data/raw/anac/{Path(str(entry['arquivo'])).name}"
    aliases=[]
    for row in rows:
        code=row["aeroporto_id"]
        row["arquivo_movimentos"]="data/raw/anac/Dados_Estatisticos.csv"
        row["arquivo_cadastro"]=f"data/raw/anac/{Path(str(row['arquivo_cadastro'])).name}"
        if code in siros and row["flag_qualidade"] == "ok":
            row["flag_qualidade"]="catalogo_anac_e_siros"
        if row.get("ciad") and row["ciad"] != code: aliases.append({"alias":row["ciad"],"aeroporto_id":code,"tipo":"CIAD","fonte":"cadastro ANAC"})
    resource_counts={}
    for resource_id,path,infra in (("publicos",collector.public_path,"AERODROMO"),("privativos",collector.private_path,"AERODROMO"),("helipontos",collector.heliports_path,"HELIPONTO"),("helidecks",collector.helidecks_path,"HELIDECK"),("siros",collector.siros_path,"SIROS")):
        count,schema=count_resource(path) if resource_id != "siros" else (len(siros),next(iter(siros.values())).keys())
        resource_counts[resource_id]={"registros_brutos":count,"schema":list(schema),"tipo_infraestrutura":infra,"excluidos_por_tipo":count if infra in {"HELIPONTO","HELIDECK"} else 0,"restantes":0 if infra in {"HELIPONTO","HELIDECK"} else count}
    cases={code:{key:row.get(key) for key in ("situacao_cadastral","validade","cadastro_pos_corte","data_efetiva_cadastro","eligibilidade_operacional","decisao_cadastral_temporal","elegivel","motivo_exclusao","flag_qualidade")} for code in ("SNVS","SBCA","SBDN","SBRJ","SBTU","SJZA","SNGI","SNPD") for row in rows if row.get("oaci")==code}
    qa.update({"recursos_cadastrais":resource_counts,"infraestruturas_excluidas_por_tipo":{"HELIPONTO":resource_counts["helipontos"]["registros_brutos"],"HELIPORTO":0,"HELIDECK":resource_counts["helidecks"]["registros_brutos"]},"campos_oficiais_ausentes":{field:sum(not str(r.get(field,"")) for r in rows) for field in ("ciad","validade","situacao_cadastral","tipo_infraestrutura")},"cadastros_pos_corte":{"data_corte":"2026-08-12","quantidade":sum(bool(r["cadastro_pos_corte"]) for r in rows),"uso":"crosswalk_auxiliar_e_portao_conservador_para_adversidades"},"regra_validade_registro":{"norma":"Resolução ANAC nº 736/2024, arts. 5º, 7º, 8º e 10","interpretacao":"validade histórica não bloqueante; inscrição sob o novo regime é por tempo indeterminado","bloqueia_isoladamente":False},"decisoes_cadastrais_temporais":cases,"siros":{"registros":len(siros),"codigos_catalogo_confirmados":sum(r["aeroporto_id"] in siros for r in rows),"ssou":siros.get("SSOU")},"aliases":{"total":len(aliases)},"coordenadas_invalidas":[]})
    qa.update(assess_publication_integrity(rows, qa))
    failed_gates=[name for name,passed in qa["portoes_publicacao"].items() if not passed]
    if failed_gates:
        raise RuntimeError("portões de publicação ANAC falharam: " + ", ".join(failed_gates))
    eligible=[r for r in rows if r["elegivel"]]; discarded=[r for r in rows if not r["elegivel"]]
    evidence,routes=_osrm_evidence(report); airport_map={r["aeroporto_id"]:r for r in eligible}; sensitivity=compare_access_scenarios(routes,airport_map)
    manifest={"fonte":"ANAC","periodo":"2025-07/2026-06","status":"success","artefatos":result.manifest_entries,"recursos_cadastrais":resource_counts,"transformacao":{"contagens":{"catalogo_unificado":len(rows),"elegiveis":len(eligible)},"coverage_complete":qa["coverage_complete"],"outputs":["aeroportos_servico.csv","aeroportos_elegiveis.csv","aeroportos_descartados.csv","origens_externas.csv","origens_brasileiras_sem_cadastro.csv","aliases_aeroportos.csv","qa.json","manifest.json","sensibilidade.csv","osrm-sensitivity-sample.json"]}}
    files={out/"aeroportos_servico.csv":(rows,OUTPUT_FIELDS),out/"aeroportos_elegiveis.csv":(eligible,OUTPUT_FIELDS),out/"aeroportos_descartados.csv":(discarded,OUTPUT_FIELDS),report/"origens_externas.csv":(qa["origens_externas"],EXTERNAL_FIELDS),report/"origens_brasileiras_sem_cadastro.csv":(qa["origens_brasileiras_sem_cadastro"],MISSING_FIELDS),report/"aliases_aeroportos.csv":(aliases,ALIAS_FIELDS),report/"qa.json":json.dumps(qa,ensure_ascii=False,indent=2,sort_keys=True)+"\n",report/"manifest.json":json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",report/"sensibilidade.csv":(sensitivity,None),report/"osrm-sensitivity-sample.json":json.dumps(evidence,ensure_ascii=False,indent=2,sort_keys=True)+"\n"}
    publish_atomic(files)
    return {"publicos":len(public),"privativos":len(private),"unificado":len(rows),"elegiveis":len(eligible),"qa":qa,"manifest":manifest}


if __name__=="__main__": print(json.dumps(materialize(),ensure_ascii=False,default=str))
