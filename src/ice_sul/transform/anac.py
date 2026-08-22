"""Catálogo unificado e agregação streaming dos movimentos ANAC."""
from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, Mapping

WINDOW_START, WINDOW_END = date(2025, 7, 1), date(2026, 6, 30)
MOVEMENT_FIELDS = {"EMPRESA_SIGLA", "EMPRESA_NOME", "AEROPORTO_DE_ORIGEM_SIGLA", "AEROPORTO_DE_ORIGEM_NOME", "AEROPORTO_DE_ORIGEM_UF", "AEROPORTO_DE_ORIGEM_PAIS", "AEROPORTO_DE_DESTINO_SIGLA", "AEROPORTO_DE_DESTINO_NOME", "AEROPORTO_DE_DESTINO_UF", "AEROPORTO_DE_DESTINO_PAIS", "ANO", "MES", "GRUPO_DE_VOO", "NATUREZA", "DECOLAGENS", "ASSENTOS", "PASSAGEIROS_PAGOS", "PASSAGEIROS_GRATIS"}
OUTPUT_FIELDS = ("aeroporto_id", "oaci", "ciad", "nome", "municipio_atendido", "uf", "pais", "latitude", "longitude", "tipo_cadastro", "tipo_infraestrutura", "situacao_cadastral", "validade", "cadastro_pos_corte", "data_efetiva_cadastro", "eligibilidade_operacional", "decisao_cadastral_temporal", "meses_com_servico", "meses_lista", "decolagens", "destinos_distintos", "elegivel", "motivo_exclusao", "acesso_publico_status", "operadores_observados", "rotas_observadas", "evidencia_servico_comercial", "score_exploratorio_frequencia_diversidade", "metrica_status", "periodo_inicio", "periodo_fim", "fonte_movimentos", "fonte_cadastro", "arquivo_movimentos", "arquivo_cadastro", "versao_movimentos", "versao_cadastro", "flag_qualidade")
PUBLICATION_REQUIRED_FIELDS = ("aeroporto_id", "nome", "municipio_atendido", "uf", "latitude", "longitude", "tipo_cadastro", "arquivo_movimentos", "arquivo_cadastro", "versao_movimentos", "versao_cadastro")
VALID_UFS = {"AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"}


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^A-Z0-9]+", " ", text.encode("ascii", "ignore").decode().upper()).strip()


def _code(value: object) -> str:
    raw = str(value or "").strip().upper()
    if raw and not re.fullmatch(r"[A-Z0-9]+", raw): raise ValueError(f"código ANAC contém caracteres inválidos: {value!r}")
    return raw


def _number(value: object) -> Decimal:
    text = str(value or "0").strip().replace(".", "").replace(",", ".")
    try: number = Decimal(text or "0")
    except InvalidOperation as exc: raise ValueError(f"valor numérico ANAC inválido: {value!r}") from exc
    if number < 0: raise ValueError(f"valor numérico ANAC negativo: {value!r}")
    return number


def coordinate(value: object, *, latitude: bool) -> float:
    text = str(value or "").strip().upper().replace(",", ".")
    if not text: raise ValueError("coordenada vazia")
    try: result = float(text)
    except ValueError:
        parts = re.findall(r"\d+(?:\.\d+)?", text)
        if len(parts) < 3: raise ValueError(f"coordenada ANAC inválida: {value!r}") from None
        degrees, minutes, seconds = map(float, parts[:3]); result = degrees + minutes / 60 + seconds / 3600
        if any(mark in text for mark in ("S", "W", "O")): result *= -1
    if not -(90 if latitude else 180) <= result <= (90 if latitude else 180): raise ValueError(f"coordenada fora da faixa: {value!r}")
    return result


def _open_text(path: Path):
    """Os recursos ANAC alternam entre UTF-8-BOM e Windows-1252."""
    try:
        with path.open(encoding="utf-8-sig") as probe:
            probe.read(8192)
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "cp1252"
    return path.open(encoding=encoding, newline="")


def read_aerodromes(path: Path, *, tipo_cadastro: str = "publico", tipo_infraestrutura: str = "AERODROMO") -> list[dict[str, object]]:
    """Lê integralmente um recurso cadastral, sem inventar campos ausentes."""
    rows: list[dict[str, object]] = []
    with _open_text(path) as stream:
        version = stream.readline().strip()
        reader = csv.DictReader(stream, delimiter=";")
        headers = {_key(h): h for h in (reader.fieldnames or [])}
        required = {"CODIGO OACI", "CIAD", "NOME"}
        if not required <= set(headers): raise ValueError(f"schema inesperado do cadastro de aeródromos ANAC: {sorted(required-set(headers))}")
        def get_nonempty(raw, *names):
            for name in names:
                original = headers.get(_key(name))
                if original is None:
                    continue
                value = raw.get(original, "")
                if value is not None and str(value).strip():
                    return value
            return ""
        for values in reader:
            raw = values
            if not any(raw.values()): continue
            infra = str(get_nonempty(raw, "TIPO DE INFRAESTRUTURA") or tipo_infraestrutura).strip()
            if _key(infra) in {"HELIPONTO", "HELIPORTO", "HELIDECK"}: continue
            oaci, ciad = _code(get_nonempty(raw, "CÓDIGO OACI")), _code(get_nonempty(raw, "CIAD")); identifier = oaci or ciad
            if not identifier: raise ValueError("aeródromo sem código OACI e CIAD")

            served_municipality = str(get_nonempty(raw, "MUNICÍPIO SERVIDO", "MUNICÍPIO ATENDIDO")).strip()
            served_uf = str(get_nonempty(raw, "UF SERVIDO", "UF ATENDIDO")).strip().upper()
            base_municipality = str(get_nonempty(raw, "MUNICÍPIO")).strip()
            base_uf = str(get_nonempty(raw, "UF")).strip().upper()
            if served_municipality:
                municipality = served_municipality
                uf = served_uf or base_uf
            else:
                municipality = base_municipality
                uf = base_uf

            uf_names = {"ACRE":"AC","ALAGOAS":"AL","AMAPA":"AP","AMAZONAS":"AM","BAHIA":"BA","CEARA":"CE","DISTRITO FEDERAL":"DF","ESPIRITO SANTO":"ES","GOIAS":"GO","MARANHAO":"MA","MATO GROSSO":"MT","MATO GROSSO DO SUL":"MS","MINAS GERAIS":"MG","PARA":"PA","PARAIBA":"PB","PARANA":"PR","PERNAMBUCO":"PE","PIAUI":"PI","RIO DE JANEIRO":"RJ","RIO GRANDE DO NORTE":"RN","RIO GRANDE DO SUL":"RS","RONDONIA":"RO","RORAIMA":"RR","SANTA CATARINA":"SC","SAO PAULO":"SP","SERGIPE":"SE","TOCANTINS":"TO"}
            uf = uf_names.get(_key(uf), uf)
            if uf and uf not in VALID_UFS: raise ValueError(f"UF inválida: {uf}")
            situation = str(get_nonempty(raw, "SITUAÇÃO CADASTRAL", "SITUAÇÃO")).strip()
            latitude = get_nonempty(raw, "LATGEOPOINT", "LATITUDE")
            longitude = get_nonempty(raw, "LONGEOPOINT", "LONGITUDE")
            rows.append({"aeroporto_id": identifier, "oaci": oaci, "ciad": ciad, "nome": str(get_nonempty(raw, "NOME")).strip(),
                "municipio_atendido": municipality, "uf": uf, "pais": "BRASIL",
                "latitude": coordinate(latitude, latitude=True), "longitude": coordinate(longitude, latitude=False),
                "tipo_cadastro": tipo_cadastro, "tipo_infraestrutura": infra, "situacao_cadastral": situation,
                "validade": str(get_nonempty(raw, "VALIDADE DO REGISTRO", "VALIDADE DO CADASTRO", "VALIDADE")).strip(), "fonte_arquivo": str(path), "versao_fonte": version})
    return rows


def read_siros(path: Path) -> dict[str, dict[str, str]]:
    """Lê o catálogo operacional SIROS integralmente para reconciliação."""
    with _open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter=";")
        headers = {_key(h): h for h in (reader.fieldnames or [])}
        required = {"SIGLA ICAO AERODROMO", "NOME AERODROMO", "PAIS AERODROMO", "LATITUDE", "LONGITUDE"}
        if not required <= set(headers): raise ValueError(f"schema SIROS inválido: {sorted(required-set(headers))}")
        result = {}
        for raw in reader:
            code = _code(raw[headers["SIGLA ICAO AERODROMO"]])
            if code:
                if code in result:
                    raise ValueError(f"código ICAO duplicado no SIROS: {code}")
                result[code] = {_key(k).lower().replace(" ", "_"): v for k, v in raw.items()}
        return result


def unify_aerodromes(*catalogues: Iterable[Mapping[str, object]]) -> tuple[list[dict[str, object]], dict[str, str]]:
    all_items=[dict(source) for catalogue in catalogues for source in catalogue]
    oaci_counts=Counter(_code(item.get("oaci")) for item in all_items if _code(item.get("oaci")))
    registry: dict[str, dict[str, object]] = {}; aliases: dict[str, str] = {}
    for item in all_items:
            oaci,ciad=_code(item.get("oaci")),_code(item.get("ciad"))
            identifier = ciad if oaci and oaci_counts[oaci] > 1 else (oaci or ciad)
            if not identifier: raise ValueError("aeródromo sem identificador")
            if identifier in registry: raise ValueError(f"código OACI duplicado: {identifier}")
            registry[identifier] = item; item["aeroporto_id"] = identifier
            for field in ("oaci", "ciad", "aeroporto_id"):
                alias = _code(item.get(field))
                if field == "oaci" and oaci_counts[alias] > 1: continue
                if alias and alias in aliases and aliases[alias] != identifier: raise ValueError(f"alias ambíguo: {alias}")
                if alias: aliases[alias] = identifier
    return [registry[k] for k in sorted(registry)], aliases


def _movement_reader(path: Path) -> tuple[str, Iterator[dict[str, str]]]:
    stream = path.open(encoding="utf-8-sig", newline=""); version = stream.readline().strip(); reader = csv.DictReader(stream, delimiter=";")
    missing = MOVEMENT_FIELDS - set(reader.fieldnames or ())
    if missing: stream.close(); raise ValueError(f"schema inesperado dos movimentos ANAC; ausentes: {sorted(missing)}")
    def iterator() -> Iterator[dict[str, str]]:
        try: yield from reader
        finally: stream.close()
    return version, iterator()


def read_movements(path: Path) -> tuple[str, Iterator[dict[str, str]]]:
    """Retorna iterador, nunca uma lista proporcional ao raw."""
    return _movement_reader(path)


def inspect_movements(path: Path) -> dict[str, object]:
    """Passagem 1: valida schema, conta linhas e meses sem reter registros."""
    version, rows = _movement_reader(path); months, count = set(), 0
    for row in rows:
        count += 1; months.add(f'{int(row["ANO"]):04d}-{int(row["MES"]):02d}')
    expected = {f"{y:04d}-{m:02d}" for y, m in ([(2025,m) for m in range(7,13)] + [(2026,m) for m in range(1,7)])}
    if not expected <= months: raise ValueError("janela congelada incompleta: " + ", ".join(sorted(expected-months)))
    return {"versao": version, "linhas_totais": count, "meses_disponiveis": sorted(months), "passagens": 1}


def latest_complete_window(rows: Iterable[Mapping[str, object]], *, cutoff: date = date(2026, 8, 12)) -> tuple[date, date]:
    """Contrato da edição: snapshot congelado em julho/2025--junho/2026."""
    months = {f'{int(r["ANO"]):04d}-{int(r["MES"]):02d}' for r in rows}
    expected = {f"{y:04d}-{m:02d}" for y,m in ([(2025,m) for m in range(7,13)] + [(2026,m) for m in range(1,7)])}
    if not expected <= months: raise ValueError("janela incompleta: " + ", ".join(sorted(expected-months)))
    return WINDOW_START, WINDOW_END


def is_regular_passenger(row: Mapping[str, object]) -> bool:
    return _key(row.get("GRUPO_DE_VOO")) == "REGULAR" and (_number(row.get("ASSENTOS")) > 0 or _number(row.get("PASSAGEIROS_PAGOS")) + _number(row.get("PASSAGEIROS_GRATIS")) > 0)


def _is_brazil(country: object, uf: object) -> bool:
    return _key(country) in {"BRASIL", "BRAZIL", "BR"} or str(uf or "").strip().upper() in VALID_UFS


def _build(aerodromes: Iterable[Mapping[str, object]], movements: Iterable[Mapping[str, object]], *, total_lines: int | None = None, aliases_explicit: Mapping[str, str] | None = None) -> tuple[list[dict[str, object]], dict[str, object]]:
    catalogue, aliases = unify_aerodromes(aerodromes); explicit = {_code(k): _code(v) for k,v in (aliases_explicit or {}).items()}
    for alias, target in explicit.items():
        if target not in {r["aeroporto_id"] for r in catalogue}: raise ValueError(f"alias aponta para aeroporto inexistente: {target}")
        if alias in aliases and aliases[alias] != target: raise ValueError(f"alias ambíguo: {alias}")
        aliases[alias] = target
    registry = {str(r["aeroporto_id"]): r for r in catalogue}; months=defaultdict(set); departures=defaultdict(Decimal); destinations=defaultdict(set); operators=defaultdict(set); routes=defaultdict(set)
    missing: dict[str, dict[str, object]] = {}; external: dict[str, dict[str, object]] = {}; counts=Counter(); domains={k:set() for k in ("grupo_de_voo","natureza","pais_origem","uf_origem")}; destination_stats=Counter()
    for row in movements:
        counts["linhas_totais"] += 1
        month = date(int(str(row["ANO"])), int(str(row["MES"])), 1)
        if not WINDOW_START <= month <= WINDOW_END: counts["linhas_fora_janela"] += 1; continue
        counts["linhas_na_janela"] += 1
        domains["grupo_de_voo"].add(str(row.get("GRUPO_DE_VOO", ""))); domains["natureza"].add(str(row.get("NATUREZA", ""))); domains["pais_origem"].add(str(row.get("AEROPORTO_DE_ORIGEM_PAIS", ""))); domains["uf_origem"].add(str(row.get("AEROPORTO_DE_ORIGEM_UF", "")))
        if _key(row.get("GRUPO_DE_VOO")) != "REGULAR": counts["linhas_nao_regulares"] += 1; continue
        counts["linhas_regulares"] += 1
        if not is_regular_passenger(row): counts["linhas_sem_servico_passageiros"] += 1; continue
        counts["linhas_regulares_passageiros"] += 1; amount=_number(row.get("DECOLAGENS"))
        if amount <= 0: counts["linhas_sem_decolagem_positiva"] += 1; continue
        counts["linhas_com_decolagem_positiva"] += 1
        origin_code=_code(row.get("AEROPORTO_DE_ORIGEM_SIGLA")); origin=aliases.get(origin_code)
        brazil=origin is not None or _is_brazil(row.get("AEROPORTO_DE_ORIGEM_PAIS"),row.get("AEROPORTO_DE_ORIGEM_UF"))
        if not brazil:
            info=external.setdefault(origin_code or "<VAZIO>", {"codigo":origin_code,"nome":row.get("AEROPORTO_DE_ORIGEM_NOME", ""),"pais":row.get("AEROPORTO_DE_ORIGEM_PAIS", ""),"meses":set(),"decolagens":Decimal()}); info["meses"].add(month.strftime("%Y-%m")); info["decolagens"] += amount; continue
        counts["decolagens_regulares_passageiros_origem_brasil"] += amount
        if not origin:
            info=missing.setdefault(origin_code or "<VAZIO>", {"codigo":origin_code,"nome":row.get("AEROPORTO_DE_ORIGEM_NOME", ""),"uf":row.get("AEROPORTO_DE_ORIGEM_UF", ""),"pais":row.get("AEROPORTO_DE_ORIGEM_PAIS", ""),"meses":set(),"decolagens":Decimal(),"destinos":set()}); info["meses"].add(month.strftime("%Y-%m")); info["decolagens"] += amount; info["destinos"].add(_code(row.get("AEROPORTO_DE_DESTINO_SIGLA"))); counts["decolagens_origens_brasileiras_nao_ligadas"] += amount; continue
        counts["decolagens_origens_ligadas"] += amount; months[origin].add(month.strftime("%Y-%m")); departures[origin] += amount
        operator = str(row.get("EMPRESA_NOME") or row.get("EMPRESA_SIGLA") or "").strip()
        if operator: operators[origin].add(operator)
        destination_code=_code(row.get("AEROPORTO_DE_DESTINO_SIGLA")); linked_destination=aliases.get(destination_code)
        destination_brazil=linked_destination is not None or _is_brazil(row.get("AEROPORTO_DE_DESTINO_PAIS"),row.get("AEROPORTO_DE_DESTINO_UF"))
        if not destination_code: destination_stats["vazios"] += 1; continue
        if destination_brazil:
            normalized=linked_destination
            if not normalized: destination_stats["brasileiros_nao_ligados"] += 1; normalized=f"BR_NAO_LIGADO:{destination_code}"
            else: destination_stats["brasileiros_ligados"] += 1
        else: normalized=f"EXT:{destination_code}"; destination_stats["estrangeiros"] += 1
        if normalized == origin: destination_stats["self_loops_removidos"] += 1; continue
        destinations[origin].add(normalized)
        routes[origin].add(f"{origin}-{normalized}")
    if total_lines is not None and counts["linhas_totais"] != total_lines: raise ValueError("passagens produziram contagens divergentes")
    output=[]
    for identifier,item in registry.items():
        active=sorted(months[identifier]); operational=len(active)>=6; amount=departures[identifier]; diversity=len(destinations[identifier])
        commercial = bool(operational and operators[identifier] and routes[identifier])
        private = item.get("tipo_cadastro") == "privativo"
        eligible = operational and (commercial if private else True)
        reason = "" if eligible else ("cadastro sem decolagem regular de passageiros na janela" if not active else "serviço em menos de 6 meses da janela" if not operational else "serviço comercial utilizável não demonstrado")
        access_status = "servico_regular_comercial_observado" if commercial else ("nao_demonstrado" if private else "nao_aplicavel")
        quality = "ok" if eligible else ("indeterminado_servico_comercial" if private and operational else "ok")
        version_match=re.search(r"(\d{4})-(\d{2})-(\d{2})", str(item.get("versao_fonte", "")))
        effective=date(*map(int,version_match.groups())) if version_match else None
        post_cut=bool(effective and effective > date(2026,8,12))
        temporal="crosswalk_pos_corte_sem_evidencia_adversa" if post_cut else "contemporaneo_ao_corte"
        status=_key(item.get("situacao_cadastral"))
        validity=None
        if str(item.get("validade", "")).strip():
            try:
                day,month,year=map(int,str(item["validade"]).split("/")); validity=date(year,month,day)
                temporal="validade_historica_nao_bloqueante_resolucao_736" if status == "CADASTRADO" else temporal
            except (ValueError,TypeError):
                temporal="indeterminado_validade_invalida"; eligible=False; quality="indeterminado_validade_no_corte"; reason="formato de validade cadastral inválido"
        if status in {"INTERDITADO","CANCELADO","EXCLUIDO","SUSPENSO"}:
            eligible=False; temporal="indeterminado_situacao_pos_corte" if post_cut else "situacao_incompativel_no_corte"; quality="indeterminado_situacao_no_corte"; reason="situação cadastral incompatível ou temporalmente indeterminada no corte"
        output.append({**{field:item.get(field,"") for field in OUTPUT_FIELDS}, **item, "cadastro_pos_corte":post_cut,"data_efetiva_cadastro":effective.isoformat() if effective else "","eligibilidade_operacional":operational,"decisao_cadastral_temporal":temporal,"meses_com_servico":len(active),"meses_lista":";".join(active),"decolagens":int(amount) if amount==int(amount) else str(amount),"destinos_distintos":diversity,"elegivel":eligible,"motivo_exclusao":reason,"acesso_publico_status":access_status,"operadores_observados":";".join(sorted(operators[identifier])),"rotas_observadas":";".join(sorted(routes[identifier])),"evidencia_servico_comercial":"Dados Estatísticos ANAC: grupo REGULAR com assentos/passageiros e decolagens positivos" if commercial else "","score_exploratorio_frequencia_diversidade":math.sqrt(float(amount)*diversity) if operational else None,"metrica_status":"exploratoria_nao_congelada","periodo_inicio":WINDOW_START.isoformat(),"periodo_fim":WINDOW_END.isoformat(),"fonte_movimentos":"ANAC Dados Estatísticos","fonte_cadastro":"ANAC cadastros público e privativo","arquivo_cadastro":item.get("fonte_arquivo",""),"versao_cadastro":item.get("versao_fonte",""),"flag_qualidade":quality})
    missing_rows=[]
    for info in missing.values():
        active=sorted(info.pop("meses")); dest=info.pop("destinos"); missing_rows.append({**info,"meses_com_servico":len(active),"meses_lista":";".join(active),"decolagens":int(info["decolagens"]),"destinos_distintos":len(dest),"atingiria_limiar_se_ligada":len(active)>=6,"motivo_ausencia":"não localizado no catálogo oficial unificado","fontes_oficiais_investigadas":"cadastros ANAC público V2, privativo V2 e SIROS","conclusao":"pendente de de/para oficial"})
    external_rows=[]
    for info in external.values():
        active=sorted(info.pop("meses")); external_rows.append({**info,"meses_com_servico":len(active),"meses_lista":";".join(active),"decolagens":int(info["decolagens"])})
    rec={"linhas_totais":counts["linhas_totais"]==counts["linhas_fora_janela"]+counts["linhas_na_janela"],"linhas_na_janela":counts["linhas_na_janela"]==counts["linhas_nao_regulares"]+counts["linhas_regulares"],"linhas_regulares":counts["linhas_regulares"]==counts["linhas_sem_servico_passageiros"]+counts["linhas_regulares_passageiros"],"linhas_regulares_passageiros":counts["linhas_regulares_passageiros"]==counts["linhas_sem_decolagem_positiva"]+counts["linhas_com_decolagem_positiva"],"decolagens_origem_brasil":counts["decolagens_regulares_passageiros_origem_brasil"]==counts["decolagens_origens_ligadas"]+counts["decolagens_origens_brasileiras_nao_ligadas"]}
    qa={"janela":{"inicio":WINDOW_START.isoformat(),"fim":WINDOW_END.isoformat()},"contagens_filtros":{k:int(v) for k,v in counts.items()},"aerodromos_cadastro":len(registry),"aerodromos_publicos":sum(r.get("tipo_cadastro")=="publico" for r in catalogue),"aerodromos_privativos":sum(r.get("tipo_cadastro")=="privativo" for r in catalogue),"aerodromos_elegiveis":sum(r["elegivel"] for r in output),"elegiveis_por_tipo_cadastro":dict(Counter(r["tipo_cadastro"] for r in output if r["elegivel"])),"elegiveis_por_uf":dict(sorted(Counter(r["uf"] for r in output if r["elegivel"]).items())),"origens_brasileiras_sem_cadastro":missing_rows,"origens_externas":external_rows,"destinos":dict(destination_stats),"aliases_aplicados":explicit,"dominios_observados":{k:sorted(v) for k,v in domains.items()},"reconciliacoes":rec,"coverage_complete":not any(r["atingiria_limiar_se_ligada"] for r in missing_rows),"streaming":{"passagens":2,"linhas_retidas":False}}
    return sorted(output,key=lambda r:r["aeroporto_id"]),qa


def build_airport_scores(aerodromes: Iterable[Mapping[str, object]], movements: Iterable[Mapping[str, object]], *, cutoff: date=date(2026,8,12), aliases_explicit: Mapping[str,str]|None=None) -> tuple[list[dict[str,object]],dict[str,object]]:
    return _build(aerodromes,movements,aliases_explicit=aliases_explicit)


def build_airport_scores_streaming(aerodromes: Iterable[Mapping[str,object]], movements_path: Path, *, aliases_explicit: Mapping[str,str]|None=None) -> tuple[list[dict[str,object]],dict[str,object]]:
    inspection=inspect_movements(movements_path); version,rows=_movement_reader(movements_path); output,qa=_build(aerodromes,rows,total_lines=int(inspection["linhas_totais"]),aliases_explicit=aliases_explicit)
    for row in output: row["arquivo_movimentos"]=str(movements_path); row["versao_movimentos"]=version
    qa["versao_movimentos"]=version; qa["meses_disponiveis"]=inspection["meses_disponiveis"]
    return output,qa



def assess_publication_integrity(rows: Iterable[Mapping[str, object]], qa: Mapping[str, object]) -> dict[str, object]:
    """Calcula portões que precisam estar verdes antes de qualquer promoção de outputs."""
    materialized = [dict(row) for row in rows]
    operational = [row for row in materialized if bool(row.get("eligibilidade_operacional"))]
    eligible = [row for row in materialized if bool(row.get("elegivel"))]

    def missing_territorial(scope: Iterable[Mapping[str, object]]) -> dict[str, int]:
        scope = list(scope)
        return {
            "municipio_atendido": sum(not str(row.get("municipio_atendido", "")).strip() for row in scope),
            "uf": sum(not str(row.get("uf", "")).strip() for row in scope),
        }

    missing_required = {
        field: sum(not str(row.get(field, "")).strip() for row in eligible)
        for field in PUBLICATION_REQUIRED_FIELDS
    }
    ids = [str(row.get("aeroporto_id", "")).strip() for row in eligible]
    coordinates_ok = True
    for row in eligible:
        try:
            latitude = float(row.get("latitude"))
            longitude = float(row.get("longitude"))
            if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                coordinates_ok = False
                break
        except (TypeError, ValueError):
            coordinates_ok = False
            break

    reconciliations = qa.get("reconciliacoes", {})
    reconciliations_ok = bool(reconciliations) and all(bool(value) for value in reconciliations.values())
    gates = {
        "campos_obrigatorios_elegiveis": all(value == 0 for value in missing_required.values()),
        "ufs_validas": all(str(row.get("uf", "")).strip().upper() in VALID_UFS for row in eligible),
        "coordenadas_validas": coordinates_ok,
        "ids_unicos": bool(ids) and len(ids) == len(set(ids)) and all(ids),
        "reconciliacoes": reconciliations_ok,
        "coverage_complete": bool(qa.get("coverage_complete")),
    }
    return {
        "campos_territoriais_ausentes": {
            "catalogo": missing_territorial(materialized),
            "operacionalmente_qualificados": missing_territorial(operational),
            "elegiveis": missing_territorial(eligible),
        },
        "campos_obrigatorios_ausentes_elegiveis": missing_required,
        "portoes_publicacao": gates,
    }

def write_csv(rows: list[Mapping[str,object]], destination: Path, fields: Iterable[str]|None=None) -> None:
    destination.parent.mkdir(parents=True,exist_ok=True); fieldnames=list(fields or (rows[0].keys() if rows else []))
    with destination.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fieldnames,extrasaction="ignore",lineterminator="\n"); writer.writeheader(); writer.writerows(rows)


def write_airport_scores(rows: list[Mapping[str,object]], destination: Path) -> None:
    if not rows or not any(bool(r.get("elegivel")) for r in rows): raise ValueError("snapshot ANAC vazio ou sem aeroporto elegível não pode ser publicado")
    write_csv(rows,destination,OUTPUT_FIELDS)


def publish_atomic(files: Mapping[Path, tuple[list[Mapping[str,object]],Iterable[str]|None] | str]) -> None:
    """Materializa tudo em staging e substitui o conjunto somente após validação."""
    if not files: raise ValueError("conjunto de publicação vazio")
    common = Path(os.path.commonpath([str(p.resolve()) for p in files]))
    if not common.is_dir(): common = common.parent
    common.mkdir(parents=True, exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=".anac-staging-",dir=common))
    prepared=[]; promoted=[]; backups=[]
    try:
        for index,(target,payload) in enumerate(files.items()):
            temp=staging/f"{index}-{target.name}"
            if isinstance(payload,str): temp.write_text(payload,encoding="utf-8",newline="\n")
            else: write_csv(payload[0],temp,payload[1])
            if not temp.exists() or temp.stat().st_size==0: raise ValueError(f"output vazio: {target}")
            prepared.append((temp,target))
        for index,(temp,target) in enumerate(prepared):
            target.parent.mkdir(parents=True,exist_ok=True)
            backup=staging/f"backup-{index}"
            if target.exists(): os.replace(target,backup); backups.append((backup,target))
            os.replace(temp,target); promoted.append(target)
    except Exception:
        for target in reversed(promoted): target.unlink(missing_ok=True)
        for backup,target in reversed(backups):
            if backup.exists(): os.replace(backup,target)
        raise
    finally: shutil.rmtree(staging,ignore_errors=True)
