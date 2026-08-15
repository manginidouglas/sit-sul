"""Harmonização conservadora da malha rodoviária elegível ao INF-LOG-01."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

UFS = {"PR", "SC", "RS"}
JURISDICTIONS = {"federal", "estadual"}
PAVED = {"pav", "pavimentada", "pavimentado", "pista dupla", "duplicada"}
OPERATIONAL = {"em operacao", "operacional", "existente", "implantada"}
EXCLUDED_STATUS = {"planejada", "em planejamento", "leito natural", "em implantacao"}


def canonical_text(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.strip().lower())


def canonical_road_id(value: Any, uf: str | None = None, jurisdiction: str | None = None) -> str | None:
    text = canonical_text(value)
    if not text:
        return None
    compact = re.sub(r"[^a-z0-9]", "", text).upper()
    compact = re.sub(r"^BRS", "BR", compact)
    compact = re.sub(r"^(ERS|RSC)", "RS", compact)
    match = re.search(r"(BR|PR|SC|RS)(\d{1,3})(?:([A-Z]))?", compact)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):03d}{match.group(3) or ''}"
    match = re.search(r"(\d{1,3})(?:([A-Z]))?", compact)
    prefix = "BR" if jurisdiction == "federal" else uf
    return f"{prefix}-{int(match.group(1)):03d}{match.group(2) or ''}" if match and prefix in {*UFS, "BR"} else None


def concession_value(value: Any) -> bool | None:
    text = canonical_text(value)
    if text is None:
        return None
    if text in {"nao", "nenhuma", "sem concessao", "false", "0"}:
        return False
    if text in {"sim", "true", "1"} or any(token in text for token in ("concession", "egr", "arteris", "ecocataratas")):
        return True
    return None


def _coordinates(geometry: dict[str, Any]) -> list[list[list[float]]]:
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return coords
    return []


def valid_geometry(geometry: Any) -> bool:
    if not isinstance(geometry, dict):
        return False
    lines = _coordinates(geometry)
    return bool(lines) and all(
        len(line) >= 2 and all(
            isinstance(point, (list, tuple)) and len(point) >= 2
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in point[:2])
            and -180 <= point[0] <= 180 and -90 <= point[1] <= 90
            for point in line
        ) for line in lines
    )


def geometry_km(geometry: dict[str, Any]) -> float:
    """Comprimento geodésico aproximado (haversine), adequado ao QA, não à rota."""
    total = 0.0
    for line in _coordinates(geometry):
        for a, b in zip(line, line[1:]):
            lon1, lat1, lon2, lat2 = map(math.radians, (*a[:2], *b[:2]))
            dlat, dlon = lat2 - lat1, lon2 - lon1
            h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            total += 2 * 6371.0088 * math.asin(math.sqrt(h))
    return total


def normalize_feature(feature: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    p = feature.get("properties") or {}
    def first(*names: str) -> Any:
        return next((p[name] for name in names if name in p and p[name] not in (None, "")), None)
    uf = str(first("uf", "UF", "sg_uf") or source.get("uf", "")).upper()
    source_id = source.get("source_id")
    raw_admin = first("ds_jurisdi", "administracao", "Jurisdicao", "TipoJuris", "jurisdicao", "jurisdiction", "administra")
    raw_surface = first("ds_superfi", "revestimento", "pavimento", "surface", "tipo_pista")
    raw_status = first("sg_legenda", "situacao_fisica", "Situacao", "SGSITUACAO", "DESITUACAO", "ds_legenda", "situacao", "status", "condicao", "sit_fisica")
    jurisdiction = canonical_text(raw_admin or source.get("jurisdiction"))
    if jurisdiction and jurisdiction.startswith("federal"): jurisdiction = "federal"
    elif jurisdiction and (jurisdiction.startswith("estadual") or jurisdiction == "planejada estadual"): jurisdiction = "estadual"
    elif jurisdiction and jurisdiction.startswith("municipal"): jurisdiction = "municipal"
    pavement = canonical_text(raw_surface)
    status = canonical_text(raw_status)
    if source_id == "dnit_snv":
        legend = str(first("sg_legenda") or "").upper()
        surface = str(first("ds_superfi") or "").upper()
        work = str(first("ds_obra") or "").upper()
        status = {"PAV": "operacional", "DUP": "operacional", "PLA": "planejada",
                  "IMP": "em implantacao", "EOD": "indeterminada", "EOP": "indeterminada",
                  "TRV": "indeterminada"}.get(legend, "indeterminada")
        pavement = "pav" if surface == "PAV" and legend in {"PAV", "DUP"} else canonical_text(surface)
        if work in {"EOD", "EOP"} and legend in {"PAV", "DUP"}:
            status = "indeterminada"
    elif source_id == "daer_rs":
        physical = canonical_text(first("situacao_fisica"))
        if physical in {"pavimentada", "duplicada"}:
            status, pavement = "operacional", physical
        elif physical in {"implantada", "planejada", "em obras de pavimentacao", "em obras de duplicacao"}:
            status = physical
        else:
            status = "indeterminada"
    elif source_id == "der_pr":
        physical = canonical_text(first("Situacao"))
        if physical:
            status = "operacional" if physical in {"pav", "dup", "pavimentada", "duplicada", "existente"} else physical
            pavement = "pavimentada" if physical in {"pav", "dup", "pavimentada", "duplicada"} else pavement
    elif source_id == "geosie_sc":
        physical = canonical_text(first("SGSITUACAO", "DESITUACAO"))
        if physical:
            status = "operacional" if physical in {"pav", "pavimentada", "dup", "duplicada"} else physical
            pavement = "pavimentada" if status == "operacional" else pavement
    road_id = canonical_road_id(first("vl_br", "Rod_Txt", "SGRODOVIA", "nome", "rodovia", "codigo", "sigla", "br", "route"), uf, jurisdiction)
    geometry = feature.get("geometry")
    eligible = (uf in UFS and jurisdiction in JURISDICTIONS and pavement in PAVED
                and status in OPERATIONAL and valid_geometry(geometry))
    reason = None
    if not eligible:
        if uf not in UFS: reason = "uf_fora_territorio"
        elif jurisdiction not in JURISDICTIONS: reason = "jurisdicao_inelegivel_ou_ausente"
        elif pavement not in PAVED: reason = "pavimento_inelegivel_ou_ausente"
        elif status in EXCLUDED_STATUS or status not in OPERATIONAL: reason = "situacao_inelegivel_ou_ausente"
        else: reason = "geometria_invalida"
    props = {
        "segmento_id": None, "rodovia_id": road_id, "jurisdicao": jurisdiction,
        "situacao": status, "pavimento": pavement, "uf": uf,
        "vigencia_data": source.get("reference_date"), "fonte_id": source.get("source_id"),
        "fonte_instituicao": source.get("institution"), "concessao": concession_value(first("concessao", "Concessao", "concessionaria")),
        "elegivel": eligible, "motivo_exclusao": reason,
        "chave_oficial": first("vl_codigo", "Trecho", "NUGEO", "codigo_sre", "codigo"),
        "categoria_situacao_original": raw_status,
        "categoria_pavimento_original": raw_surface,
        "categoria_administracao_original": raw_admin,
    }
    fingerprint = json.dumps([source_id, props["chave_oficial"] or [road_id, uf, jurisdiction, geometry]], sort_keys=True, separators=(",", ":"))
    props["segmento_id"] = hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
    props["extensao_km_qa"] = round(geometry_km(geometry), 6) if valid_geometry(geometry) else None
    return {"type": "Feature", "properties": props, "geometry": geometry}


def process(features_by_source: Iterable[tuple[dict[str, Any], Iterable[dict[str, Any]]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_rows = [normalize_feature(feature, source) for source, features in features_by_source for feature in features]
    eligible = [row for row in all_rows if row["properties"]["elegivel"]]
    ids = Counter(row["properties"]["segmento_id"] for row in eligible)
    totals: dict[str, dict[str, dict[str, float | int]]] = defaultdict(lambda: defaultdict(lambda: {"segmentos": 0, "km": 0.0}))
    for row in eligible:
        p = row["properties"]; cell = totals[p["uf"]][p["jurisdicao"]]
        cell["segmentos"] += 1; cell["km"] += p["extensao_km_qa"]
    report = {
        "generated_on": date.today().isoformat(), "crs": "EPSG:4326",
        "segmentos_recebidos": len(all_rows), "segmentos_elegiveis": len(eligible),
        "missing_situacao": sum(r["properties"]["situacao"] is None for r in all_rows),
        "missing_pavimento": sum(r["properties"]["pavimento"] is None for r in all_rows),
        "duplicidades": sum(n - 1 for n in ids.values() if n > 1),
        "geometrias_invalidas": sum(not valid_geometry(r["geometry"]) for r in all_rows),
        "exclusoes_por_motivo": dict(Counter(r["properties"]["motivo_exclusao"] for r in all_rows if not r["properties"]["elegivel"])),
        "cobertura": {uf: {jur: {"segmentos": v["segmentos"], "km": round(v["km"], 3)} for jur, v in jurisdictions.items()} for uf, jurisdictions in totals.items()},
    }
    return eligible, report


def write_outputs(eligible: list[dict[str, Any]], report: dict[str, Any], output: Path, qa: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True); qa.parent.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "name": "rodovias_estruturantes_elegiveis", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}, "features": eligible}
    output.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    qa.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


SOURCE_SCHEMAS = {
    "dnit_snv": {"sg_uf", "vl_br", "vl_codigo", "ds_tipo_ad", "ds_obra", "ds_jurisdi",
                 "ds_superfi", "ds_legenda", "sg_legenda"},
    "daer_rs": {"codigo_sre", "nome", "rede", "administracao", "situacao_fisica", "revestimento",
                "concessao", "federal_superposta", "municipalizacao", "tipo_tracado"},
}
MAPPINGS = {
    "dnit_snv": {"id": "vl_codigo", "road": "vl_br", "uf": "sg_uf", "status": "sg_legenda", "surface": "ds_superfi"},
    "daer_rs": {"id": "codigo_sre", "road": "nome", "administration": "administracao", "status": "situacao_fisica", "surface": "revestimento"},
}


def apply_precedence(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aplica autoridade por jurisdição sem deduplicar segmentos da mesma fonte."""
    kept, removed = [], []
    expected_state = {"PR": "der_pr", "SC": "geosie_sc", "RS": "daer_rs"}
    for row in rows:
        p = row["properties"]
        authority = "dnit_snv" if p["jurisdicao"] == "federal" else expected_state.get(p["uf"])
        if p["fonte_id"] == authority:
            kept.append(row)
        else:
            removed.append({"segmento_descartado": p["segmento_id"], "fonte_descartada": p["fonte_id"],
                            "fonte_precedente": authority, "jurisdicao": p["jurisdicao"],
                            "rodovia": p["rodovia_id"], "tipo_decisao": "filtro_de_autoridade_sem_comparacao_espacial",
                            "regra": "autoridade_oficial_por_jurisdicao_e_uf"})
    return kept, removed
