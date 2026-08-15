"""Leitura DAER e publicação atômica das gerações rodoviárias."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
import argparse
import io
import zipfile
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

import shapefile
from pyproj import CRS, Transformer

from ice_sul.extract.rodovias import DNIT_INNER_ZIP, extract_dnit_inner_zip, load_catalog, validate_zip
from ice_sul.extract.http import TracingRedirect, UA
from ice_sul.routing import Coordinate, OSRMClient
from .rodovias import SOURCE_SCHEMAS, apply_precedence, normalize_feature, process, valid_geometry

DER_FIELDS = {"Trecho", "Rod_Txt", "Situacao", "Jurisdicao", "TipoJuris", "Concessao"}
GEOSIE_FIELDS = {"SGRODOVIA", "CDTRECHO", "NUGEO", "SGSITUACAO", "DESITUACAO"}


def daer_wfs_urls(base: str) -> dict[str, str]:
    endpoint = base.split("?", 1)[0]
    common = f"{endpoint}?tema=rod_sre&service=WFS&version=1.1.0"
    return {"capabilities": common + "&request=GetCapabilities",
            "schema": common + "&request=DescribeFeatureType&typeName=rod_sre",
            "features": common + "&request=GetFeature&typeName=rod_sre"}


def parse_daer_capabilities(xml: bytes) -> dict[str, str]:
    root = ET.fromstring(xml)
    text = lambda tag: next((e.text.strip() for e in root.iter() if e.tag.endswith(tag) and e.text), "")
    names = [e.text.strip() for e in root.iter() if e.tag.endswith("Name") and e.text]
    if "rod_sre" not in names: raise ValueError("typeName rod_sre ausente")
    return {"type_name": "rod_sre", "fees": text("Fees"), "access_constraints": text("AccessConstraints")}


def validate_daer_schema(xml: bytes) -> set[str]:
    root = ET.fromstring(xml)
    fields = {e.attrib["name"] for e in root.iter() if e.tag.endswith("element") and "name" in e.attrib}
    missing = SOURCE_SCHEMAS["daer_rs"] - fields
    if missing: raise ValueError(f"campos DAER ausentes: {sorted(missing)}")
    return fields


def parse_daer_gml(xml: bytes) -> list[dict[str, Any]]:
    """Converte GML 3.1.1 EPSG:4674 (latitude, longitude) para CRS84."""
    root = ET.fromstring(xml); features = []
    for member in (e for e in root.iter() if e.tag.endswith("featureMember")):
        node = next(iter(member), None)
        if node is None: continue
        props: dict[str, Any] = {}; lines: list[list[list[float]]] = []
        for child in node:
            key = child.tag.rsplit("}", 1)[-1]
            poslists = [p for p in child.iter() if p.tag.endswith("posList")]
            if poslists:
                for pos in poslists:
                    values = [float(v) for v in (pos.text or "").split()]
                    dimension = int(pos.attrib.get("srsDimension", 2))
                    line = [[values[i + 1], values[i]] for i in range(0, len(values), dimension)]
                    if len(line) >= 2: lines.append(line)
            elif len(child) == 0:
                props[key] = child.text.strip() if child.text else None
        geometry = {"type": "LineString", "coordinates": lines[0]} if len(lines) == 1 else {"type": "MultiLineString", "coordinates": lines}
        if lines: features.append({"type": "Feature", "properties": props, "geometry": geometry})
    return features


def _shape_features(zip_payload: bytes, layer: str, source_crs: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    names = validate_zip(zip_payload)
    lookup = {Path(n).name.lower(): n for n in names}
    required = {f"{layer}.{ext}".lower() for ext in ("shp", "shx", "dbf", "prj")}
    if not required <= lookup.keys(): raise ValueError(f"camada exata ausente: {layer}")
    with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
        reader = shapefile.Reader(shp=io.BytesIO(archive.read(lookup[f"{layer}.shp".lower()])),
                                  shx=io.BytesIO(archive.read(lookup[f"{layer}.shx".lower()])),
                                  dbf=io.BytesIO(archive.read(lookup[f"{layer}.dbf".lower()])), encoding="utf-8")
        prj = archive.read(lookup[f"{layer}.prj".lower()]).decode("utf-8", "replace")
    actual = CRS.from_wkt(prj); expected = CRS.from_user_input(source_crs)
    if not actual.equals(expected, ignore_axis_order=True): raise ValueError(f"CRS inesperado: {actual.to_string()}")
    fields = [f[0] for f in reader.fields[1:]]
    transformer = Transformer.from_crs(expected, "OGC:CRS84", always_xy=True)
    features = []
    for shape_record in reader.iterShapeRecords():
        props = dict(zip(fields, shape_record.record))
        parts = list(shape_record.shape.parts) + [len(shape_record.shape.points)]
        lines = [[[transformer.transform(x, y)[0], transformer.transform(x, y)[1]] for x, y in shape_record.shape.points[a:b]] for a, b in zip(parts, parts[1:])]
        geometry = {"type": "LineString", "coordinates": lines[0]} if len(lines) == 1 else {"type": "MultiLineString", "coordinates": lines}
        features.append({"type": "Feature", "properties": props, "geometry": geometry})
    return features, {"members": names, "fields": fields, "crs": actual.to_string(), "records": len(features)}


def read_dnit_rar(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inner, rar_members = extract_dnit_inner_zip(path)
    features, meta = _shape_features(inner, "SNV_202607A", "EPSG:4674")
    missing = SOURCE_SCHEMAS["dnit_snv"] - set(meta["fields"])
    if missing: raise ValueError(f"campos DNIT ausentes: {sorted(missing)}")
    filtered = [f for f in features if f["properties"].get("sg_uf") in {"PR", "SC", "RS"}]
    meta.update({"rar_members": rar_members, "inner_zip": DNIT_INNER_ZIP, "southern_records": len(filtered)})
    return filtered, meta


def read_der_zip(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    features, meta = _shape_features(path.read_bytes(), "SRE_2021_UTM_SIRGAS2000_22S_LN", "EPSG:31982")
    missing = DER_FIELDS - set(meta["fields"])
    if missing: raise ValueError(f"campos DER/PR ausentes: {sorted(missing)}")
    return features, meta


def read_geosie(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = path.read_bytes()
    if body.lstrip().startswith((b"<", b"<!DOCTYPE")): raise ValueError("GeoSIE devolveu HTML/XML")
    payload = json.loads(body)
    if payload.get("type") != "FeatureCollection": raise ValueError("GeoJSON GeoSIE inválido")
    features = payload.get("features", []); fields = set().union(*(f.get("properties", {}).keys() for f in features)) if features else set()
    missing = GEOSIE_FIELDS - fields
    if missing: raise ValueError(f"campos GeoSIE ausentes: {sorted(missing)}")
    if any(not valid_geometry(f.get("geometry")) for f in features): raise ValueError("geometria GeoSIE inválida")
    return features, {"fields": sorted(fields), "crs": "OGC:CRS84", "records": len(features)}


def read_daer(raw_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cap = (raw_dir / "capabilities.xml").read_bytes(); schema = (raw_dir / "schema.xsd").read_bytes(); gml = (raw_dir / "rod_sre.gml").read_bytes()
    metadata = parse_daer_capabilities(cap); metadata["fields"] = sorted(validate_daer_schema(schema))
    features = parse_daer_gml(gml); metadata.update({"crs_source": "EPSG:4674", "crs": "OGC:CRS84", "records": len(features)})
    if any(not valid_geometry(f["geometry"]) for f in features): raise ValueError("geometria/bounds DAER inválidos")
    return features, metadata


def read_daer_geojson(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_bytes())
    if payload.get("type") != "FeatureCollection": raise ValueError("GeoJSON IEDE/DAER inválido")
    features = payload.get("features", [])
    if len(features) != 1683: raise ValueError(f"contagem IEDE/DAER divergente: {len(features)}")
    fields = set().union(*(feature.get("properties", {}).keys() for feature in features))
    missing = SOURCE_SCHEMAS["daer_rs"] - fields
    if missing: raise ValueError(f"campos IEDE/DAER ausentes: {sorted(missing)}")
    if any(not valid_geometry(feature.get("geometry")) for feature in features): raise ValueError("geometria/bounds IEDE/DAER inválidos")
    return features, {"fields": sorted(fields), "crs": "OGC:CRS84", "records": len(features),
                      "service": "IEDE/DAER Rodovias_RS MapServer/0"}


def _fetch(url: str, path: Path, expected_mime: tuple[str, ...], *, timeout: int = 120) -> dict[str, Any]:
    """Baixa para temporário, rejeita páginas de erro e promove raw imutável."""
    sidecar = path.with_suffix(path.suffix + ".http.json")
    if path.exists():
        body = path.read_bytes(); digest = hashlib.sha256(body).hexdigest()
        if not sidecar.exists(): raise ValueError("raw existente sem sidecar de proveniência")
        original = json.loads(sidecar.read_text(encoding="utf-8"))
        required = {"requested_url", "final_url", "redirects", "collected_at", "http_status", "content_type", "bytes", "sha256"}
        if not required <= original.keys(): raise ValueError("sidecar não preserva proveniência HTTP completa")
        if original["bytes"] != len(body) or original["sha256"] != digest: raise ValueError("raw existente diverge da sidecar")
        return {**original, "status": "reused", "reused_at": datetime.now(UTC).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_suffix(path.suffix + ".part")
    try:
        redirect = TracingRedirect(); opener = build_opener(redirect); last_error = None
        for attempt in range(1, 5):
            try:
                with opener.open(Request(url, headers={"User-Agent": UA}), timeout=timeout) as response:
                    body = response.read(); status = response.status; final_url = response.url
                    content_type = response.headers.get_content_type().lower()
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if isinstance(exc, HTTPError) and exc.code not in {429, 502, 503, 504}: raise
                if attempt == 4: raise
                time.sleep(2 ** (attempt - 1))
        if content_type not in expected_mime: raise ValueError(f"MIME inesperado: {content_type}")
        if not body or body.lstrip().lower().startswith((b"<html", b"<!doctype html")): raise ValueError("resposta HTML/erro rejeitada")
        temporary.write_bytes(body)
        os.replace(temporary, path)
        metadata = {"status": "downloaded", "http_status": status, "content_type": content_type, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(), "requested_url": url, "final_url": final_url,
                "redirects": redirect.history, "path": str(path), "collected_at": datetime.now(UTC).isoformat()}
        sidecar_tmp = sidecar.with_suffix(sidecar.suffix + ".tmp")
        sidecar_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"); os.replace(sidecar_tmp, sidecar)
        return metadata
    finally:
        if temporary.exists(): temporary.unlink()


def _fetch_alternatives(urls: Iterable[str], path: Path, expected_mime: tuple[str, ...]) -> dict[str, Any]:
    attempts = []
    for url in urls:
        try:
            result = _fetch(url, path, expected_mime); result["failed_attempts"] = attempts
            return result
        except Exception as exc:
            attempts.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(f"alternativas oficiais esgotadas: {attempts}")


def collect_all(catalog_path: Path, raw_root: Path) -> dict[str, dict[str, Any]]:
    """Tenta todas as fontes independentemente e permite retomar raws já válidos."""
    results: dict[str, dict[str, Any]] = {}
    for source in load_catalog(catalog_path):
        root = raw_root / source.reference_date / source.source_id
        try:
            if source.source_id != "daer_rs":
                mime = ("application/zip", "application/octet-stream", "application/x-rar-compressed") if source.source_id != "geosie_sc" else ("application/json", "application/geo+json", "text/plain")
                entry = _fetch_alternatives((source.url, *source.alternative_urls), root / source.filename, mime)
                if source.source_id == "dnit_snv": features, inventory = read_dnit_rar(root / source.filename)
                elif source.source_id == "der_pr": features, inventory = read_der_zip(root / source.filename)
                else: features, inventory = read_geosie(root / source.filename)
                manifest = {"source_id": source.source_id, "status": "ok", "raw": entry, "inventory": inventory}
            else:
                entry = _fetch_alternatives((source.url, *source.alternative_urls), root / source.filename,
                                            ("application/geo+json", "application/json"))
                features, inventory = read_daer_geojson(root / source.filename)
                manifest = {"source_id": source.source_id, "status": "ok", "raw": entry, "inventory": inventory}
            manifest["feature_count"] = len(features)
            (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            results[source.source_id] = manifest
        except Exception as exc:
            evidence = {"source_id": source.source_id, "status": "blocked", "error": f"{type(exc).__name__}: {exc}", "attempted_at": datetime.now(UTC).isoformat()}
            root.mkdir(parents=True, exist_ok=True); (root / "attempt.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            results[source.source_id] = evidence
    return results


def load_collected(catalog_path: Path, raw_root: Path) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    loaded = []
    for source in load_catalog(catalog_path):
        root = raw_root / source.reference_date / source.source_id
        if source.source_id == "dnit_snv": features, _ = read_dnit_rar(root / source.filename)
        elif source.source_id == "der_pr": features, _ = read_der_zip(root / source.filename)
        elif source.source_id == "geosie_sc": features, _ = read_geosie(root / source.filename)
        else: features, _ = read_daer_geojson(root / source.filename)
        loaded.append(({"source_id": source.source_id, "institution": source.institution, "jurisdiction": source.jurisdiction,
                        "uf": source.states[0] if len(source.states) == 1 else None, "reference_date": source.reference_date}, features))
    return loaded


def mandatory_inspections(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases = {"PR": ("BR-116", "PR-323"), "SC": ("BR-101", "SC-401"), "RS": ("BR-290", "RS-040")}; report = {}
    for uf, roads in cases.items():
        for road in roads:
            selected = [r for r in rows if r["properties"]["uf"] == uf and r["properties"]["rodovia_id"] == road]
            report[f"{uf}:{road}"] = {"segments": len(selected), "km": round(sum(r["properties"]["extensao_km_qa"] for r in selected), 3),
                "sources": sorted({r["properties"]["fonte_id"] for r in selected}), "original_status": sorted({str(r["properties"]["categoria_situacao_original"]) for r in selected}),
                "jurisdictions": sorted({r["properties"]["jurisdicao"] for r in selected}), "eligible": all(r["properties"]["elegivel"] for r in selected)}
            if not selected: raise ValueError(f"inspeção obrigatória sem segmentos: {uf} {road}")
    return report


def route_candidates(rows: list[dict[str, Any]], *, max_spacing_m: float = 5_000) -> list[dict[str, Any]]:
    """Todos os vértices mais densificação geodésica com intervalo máximo de 5 km."""
    from pyproj import Geod
    geod = Geod(ellps="WGS84"); candidates = []
    for row in rows:
        props = row["properties"]
        lines = row["geometry"]["coordinates"] if row["geometry"]["type"] == "MultiLineString" else [row["geometry"]["coordinates"]]
        for line_index, line in enumerate(lines):
            dense = [line[0]]
            for start, end in zip(line, line[1:]):
                _, _, distance = geod.inv(start[0], start[1], end[0], end[1])
                interior = max(0, math.ceil(distance / max_spacing_m) - 1)
                if interior:
                    dense.extend([list(point) for point in geod.npts(start[0], start[1], end[0], end[1], interior)])
                dense.append(end)
            for candidate_index, point in enumerate(dense):
                candidates.append({"coordinate": Coordinate(latitude=point[1], longitude=point[0]),
                    "segmento_id": props["segmento_id"], "rodovia_id": props["rodovia_id"],
                    "jurisdicao": props["jurisdicao"], "uf": props["uf"], "fonte_id": props["fonte_id"],
                    "line_index": line_index, "candidate_index": candidate_index})
    return candidates


def validate_municipal_sample(municipalities: list[dict[str, Any]],
                              seats_path: Path = Path("data/interim/routing/municipal_seats_south_2022.csv")) -> None:
    import csv
    strata = {"metropolitana", "media", "pequena_eixo_estadual", "pequena_remota"}
    expected = {(uf, stratum) for uf in ("PR", "SC", "RS") for stratum in strata}
    observed = {(m.get("uf"), m.get("estrato")) for m in municipalities}
    if not expected <= observed: raise ValueError(f"amostra não cobre as 12 células: {sorted(expected - observed)}")
    ids = [str(m.get("municipio_id", "")) for m in municipalities]
    if len(ids) != len(set(ids)): raise ValueError("municipio_id duplicado na amostra")
    with seats_path.open(encoding="utf-8") as stream:
        seats = {row["municipio_id"]: row for row in csv.DictReader(stream)}
    for item in municipalities:
        seat = seats.get(item["municipio_id"])
        if not seat: raise ValueError(f"município ausente da base IBGE: {item['municipio_id']}")
        try:
            coordinate = Coordinate(float(item["latitude"]), float(item["longitude"]))
            seat_coordinate = Coordinate(float(seat["latitude"]), float(seat["longitude"]))
        except (KeyError, TypeError, ValueError) as exc: raise ValueError(f"coordenada municipal inválida: {item.get('municipio_id')}") from exc
        if item.get("municipio_nome") != seat["municipio_nome"] or item.get("uf") != seat["uf_sigla"]:
            raise ValueError(f"nome/UF diverge da base IBGE: {item['municipio_id']}")
        if abs(coordinate.latitude - seat_coordinate.latitude) > 1e-6 or abs(coordinate.longitude - seat_coordinate.longitude) > 1e-6:
            raise ValueError(f"coordenada diverge da sede IBGE: {item['municipio_id']}")
        for field in ("populacao_2022", "pertence_arranjo_metropolitano", "justificativa_estrato"):
            if field not in item or item[field] in (None, ""): raise ValueError(f"variável de estratificação ausente: {field}")


def osrm_study(rows: list[dict[str, Any]], municipalities: list[dict[str, Any]], client: OSRMClient,
               *, max_spacing_m: float = 5_000, snap_threshold_m: float = 1_000) -> dict[str, Any]:
    validate_municipal_sample(municipalities)
    all_candidates = route_candidates(rows, max_spacing_m=max_spacing_m)
    destinations = {"federal": [c for c in all_candidates if c["jurisdicao"] == "federal"],
                    "federal_estadual": all_candidates}
    output = [{k: value for k, value in municipality.items() if k not in {"latitude", "longitude"}}
              for municipality in municipalities]
    geod = __import__("pyproj").Geod(ellps="WGS84")
    for municipality, record in zip(municipalities, output):
        origin = Coordinate(municipality["latitude"], municipality["longitude"])
        for scenario, candidates in destinations.items():
            ordered = sorted(candidates, key=lambda candidate: geod.inv(origin.longitude, origin.latitude,
                candidate["coordinate"].longitude, candidate["coordinate"].latitude)[2])
            best = None; evaluated = 0
            # Branch-and-bound: 140 km/h is a conservative upper bound for this
            # car graph. A farther candidate cannot beat the current route once
            # even its straight-line lower-bound travel time is larger.
            for start, stop, matrix in client.table_chunks([origin], [c["coordinate"] for c in ordered], max_cells=500, distances=True):
                for index, (duration, distance) in enumerate(zip(matrix.durations_minutes[0], matrix.distances_meters[0])):
                    if duration is not None and (best is None or duration < best[0]):
                        best = (duration, distance, matrix.source_snap_distances_meters[0],
                                matrix.destination_snap_distances_meters[index], ordered[start + index])
                evaluated = stop
                if best and stop < len(ordered):
                    next_candidate = ordered[stop]["coordinate"]
                    lower_bound_m = geod.inv(origin.longitude, origin.latitude, next_candidate.longitude, next_candidate.latitude)[2]
                    if lower_bound_m / 140_000 * 60 > best[0]: break
            if best:
                winner = best[4]; record[scenario] = {"duration_minutes": best[0], "distance_meters": best[1], "origin_snap_meters": best[2],
                    "destination_snap_meters": best[3], "excessive_snap": best[2] is None or best[3] is None or best[2] > snap_threshold_m or best[3] > snap_threshold_m,
                    "segmento_id": winner["segmento_id"], "rodovia_id": winner["rodovia_id"], "jurisdicao": winner["jurisdicao"],
                    "uf": winner["uf"], "fonte_id": winner["fonte_id"], "candidate": {"latitude": winner["coordinate"].latitude,
                    "longitude": winner["coordinate"].longitude}, "route_failure": False,
                    "candidates_total": len(ordered), "candidates_evaluated": evaluated,
                    "search_bound_max_speed_kmh": 140}
            else: record[scenario] = {"route_failure": True, "error": "NoRoute para todos os candidatos"}
    for record in output:
        if "duration_minutes" in record["federal"] and "duration_minutes" in record["federal_estadual"]:
            difference = record["federal"]["duration_minutes"] - record["federal_estadual"]["duration_minutes"]
            record["difference_minutes"] = difference; record["difference_percent"] = 100 * difference / record["federal"]["duration_minutes"] if record["federal"]["duration_minutes"] else 0
    differences = [r["difference_minutes"] for r in output if "difference_minutes" in r]
    percentages = [r["difference_percent"] for r in output if "difference_percent" in r]
    difference_median = statistics.median(differences) if differences else None; percentage_median = statistics.median(percentages) if percentages else None
    substantive_decision = "inclusao_das_estaduais_altera_materialmente" if differences and (difference_median >= 5 or percentage_median >= 20) else "inclusao_melhora_marginalmente"
    excessive = {scenario: sum(row[scenario].get("excessive_snap", False) for row in output) for scenario in destinations}
    decision = substantive_decision
    if not differences or any("difference_minutes" not in r for r in output) or any(excessive.values()): decision = "exige_definicao_adicional_de_estruturante"
    return {"municipalities": output, "n": len(output), "route_failures": sum("difference_minutes" not in r for r in output),
            "difference_minutes": {"min": min(differences), "median": difference_median, "max": max(differences)} if differences else None,
            "difference_percent": {"min": min(percentages), "median": percentage_median, "max": max(percentages)} if percentages else None,
            "candidate_generation": {"max_spacing_m": max_spacing_m, "count": len(all_candidates), "uses_all_vertices": True},
            "snapping": {"threshold_m": snap_threshold_m, "excessive_winners_by_scenario": excessive,
                         "municipalities_affected": sum(any(r[s].get("excessive_snap", False) for s in destinations) for r in output)},
            "methodological_decision": decision, "substantive_decision_without_snap_gate": substantive_decision,
            "decision_threshold": "material se mediana >=5 min ou >=20%; falhas ou snapping excessivo exigem definição adicional"}


def osrm_sensitivity_study(rows: list[dict[str, Any]], municipalities: list[dict[str, Any]], client: OSRMClient,
                           *, spacings_m: tuple[float, ...] = (5_000, 1_000), snap_threshold_m: float = 1_000,
                           duration_tolerance_minutes: float = 1.0) -> dict[str, Any]:
    if len(set(spacings_m)) < 2: raise ValueError("sensibilidade exige ao menos dois espaçamentos")
    runs = {str(int(spacing)): osrm_study(rows, municipalities, client, max_spacing_m=spacing,
                                          snap_threshold_m=snap_threshold_m) for spacing in spacings_m}
    baseline = runs[str(int(spacings_m[0]))]; comparisons = []
    stable = True
    for other_spacing in spacings_m[1:]:
        other = runs[str(int(other_spacing))]
        for left, right in zip(baseline["municipalities"], other["municipalities"]):
            for scenario in ("federal", "federal_estadual"):
                same = (not left[scenario].get("route_failure") and not right[scenario].get("route_failure")
                        and left[scenario]["segmento_id"] == right[scenario]["segmento_id"]
                        and abs(left[scenario]["duration_minutes"] - right[scenario]["duration_minutes"]) <= duration_tolerance_minutes)
                comparisons.append({"municipio_id": left["municipio_id"], "scenario": scenario,
                                    "spacing_m": other_spacing, "stable": same})
                stable &= same
    no_failures = all(run["route_failures"] == 0 for run in runs.values())
    no_excessive_snap = all(not any(run["snapping"]["excessive_winners_by_scenario"].values()) for run in runs.values())
    substantive = {run["substantive_decision_without_snap_gate"] for run in runs.values()}
    same_substantive_decision = len(substantive) == 1
    decision = next(iter(substantive)) if stable and no_failures and no_excessive_snap and same_substantive_decision else "exige_definicao_adicional_de_estruturante"
    snapping = {spacing: run["snapping"]["excessive_winners_by_scenario"] for spacing, run in runs.items()}
    failures = {spacing: run["route_failures"] for spacing, run in runs.items()}
    return {"runs": runs, "comparison": comparisons, "stable": stable, "n": baseline["n"],
            "route_failures": baseline["route_failures"], "route_failures_by_spacing": failures,
            "snapping_by_spacing_and_scenario": snapping, "no_excessive_snap": no_excessive_snap,
            "same_substantive_decision": same_substantive_decision,
            "duration_tolerance_minutes": duration_tolerance_minutes, "methodological_decision": decision}


def _collection(rows: Iterable[dict[str, Any]], name: str) -> dict[str, Any]:
    return {"type": "FeatureCollection", "name": name,
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
            "features": list(rows)}


def _coverage(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    result = {f"{uf}:{jur}": 0 for uf in ("PR", "SC", "RS") for jur in ("federal", "estadual")}
    for row in rows: result[f'{row["properties"]["uf"]}:{row["properties"]["jurisdicao"]}'] += 1
    return result


def _road_stats(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter
    materialized = list(rows)
    return {"segmentos": len(materialized), "km": round(sum(r["properties"].get("extensao_km_qa") or 0 for r in materialized), 3),
            "situacao_original": dict(Counter(str(r["properties"].get("categoria_situacao_original")) for r in materialized)),
            "pavimento_original": dict(Counter(str(r["properties"].get("categoria_pavimento_original")) for r in materialized)),
            "classificacao_final": dict(Counter(str(r["properties"].get("situacao")) for r in materialized)),
            "exclusoes": dict(Counter(str(r["properties"].get("motivo_exclusao")) for r in materialized if not r["properties"].get("elegivel")))}


def publish_generation(features_by_source: Iterable[tuple[dict[str, Any], Iterable[dict[str, Any]]]],
                       destination: Path, *, generation_id: str | None = None,
                       failure_hook: Callable[[str, Path], None] | None = None,
                       before_promote: Callable[[Path], None] | None = None,
                       artifacts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publica diretório imutável e troca atomicamente apenas ``active.json``."""
    destination.mkdir(parents=True, exist_ok=True); generations = destination / "generations"; generations.mkdir(exist_ok=True)
    generation_id = generation_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    final_dir = generations / generation_id
    if final_dir.exists(): raise FileExistsError(f"geração já existe: {generation_id}")
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=generations))
    try:
        materialized = [(source, list(features)) for source, features in features_by_source]
        all_normalized = [normalize_feature(feature, source) for source, features in materialized for feature in features]
        eligible, qa = process(materialized)
        after, removals = apply_precedence(all_normalized)
        final = [r for r in after if r["properties"]["elegivel"]]
        if not final: raise ValueError("regressão bloqueada: camada elegível vazia")
        coverage = _coverage(final)
        if any(value == 0 for value in coverage.values()): raise ValueError(f"cobertura incompleta: {coverage}")
        ids = [r["properties"]["segmento_id"] for r in final]
        if len(ids) != len(set(ids)): raise ValueError("IDs de segmentos não são únicos")
        if any(not valid_geometry(r["geometry"]) for r in final): raise ValueError("geometria publicada inválida")
        essentials = ("segmento_id", "rodovia_id", "jurisdicao", "uf", "fonte_id", "chave_oficial")
        if any(any(r["properties"].get(k) in (None, "") for k in essentials) for r in final): raise ValueError("campo essencial ausente")
        products = {"universo-antes.geojson": _collection(all_normalized, "universo_antes_precedencia"),
                    "universo-depois.geojson": _collection(after, "universo_depois_precedencia"),
                    "elegiveis.geojson": _collection(final, "rodovias_elegiveis")}
        hashes = {}
        for name, payload in products.items():
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            (stage / name).write_bytes(body); hashes[name] = {"sha256": hashlib.sha256(body).hexdigest(), "registros": len(payload["features"])}
        for name, payload in (artifacts or {}).items():
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
            (stage / name).write_bytes(body); hashes[name] = {"sha256": hashlib.sha256(body).hexdigest()}
        qa.update({"segmentos_elegiveis_publicados": len(final), "cobertura_publicada": coverage,
                   "estatisticas_antes": _road_stats(all_normalized), "estatisticas_depois": _road_stats(after),
                   "estatisticas_publicadas": _road_stats(final), "geometrias_invalidas_publicadas": 0,
                   "produtos": hashes, "remocoes_precedencia": removals})
        qa_body = json.dumps(qa, ensure_ascii=False, indent=2).encode(); (stage / "qa.json").write_bytes(qa_body)
        manifest_hashes = {**hashes, "qa.json": {"sha256": hashlib.sha256(qa_body).hexdigest()}}
        (stage / "manifesto.json").write_text(json.dumps({"generation": manifest_hashes, "daer_access_constraints": "vedado o uso comercial",
            "avaliacao_uso": "uso institucional não comercial; redistribuição comercial vedada"}, ensure_ascii=False, indent=2), encoding="utf-8")
        if before_promote: before_promote(stage)  # compatibilidade do contrato anterior
        if failure_hook: failure_hook("before_generation_promote", stage)
        os.replace(stage, final_dir)
        if failure_hook: failure_hook("after_generation_promote", final_dir)
        pointer = destination / "active.json"; temporary_pointer = destination / ".active.json.tmp"
        temporary_pointer.write_text(json.dumps({"generation": generation_id, "path": f"generations/{generation_id}"}), encoding="utf-8")
        if failure_hook: failure_hook("before_pointer_swap", temporary_pointer)
        os.replace(temporary_pointer, pointer)
        if failure_hook: failure_hook("after_pointer_swap", pointer)
        return qa
    finally:
        if stage.exists(): shutil.rmtree(stage)
        temporary = destination / ".active.json.tmp"
        if temporary.exists(): temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta e materializa as quatro fontes oficiais de Rodovias")
    parser.add_argument("--catalog", type=Path, default=Path("data/raw/rodovias/catalogo-fontes.json"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/rodovias"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/rodovias/published"))
    parser.add_argument("--qa-root", type=Path, default=Path("reports/quality/mvp-demo-2026/rodovias"))
    parser.add_argument("--municipal-sample", type=Path)
    parser.add_argument("--osrm-url", default="http://127.0.0.1:5000")
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args(argv)
    collection = collect_all(args.catalog, args.raw_root)
    args.qa_root.mkdir(parents=True, exist_ok=True)
    (args.qa_root / "collection-latest.json").write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    blocked = [source for source, result in collection.items() if result["status"] != "ok"]
    if args.collect_only or blocked:
        if blocked: print(f"fontes bloqueadas: {', '.join(blocked)}")
        return 2 if blocked else 0
    loaded = load_collected(args.catalog, args.raw_root)
    materialized = [(source, list(features)) for source, features in loaded]
    normalized = [normalize_feature(feature, source) for source, features in materialized for feature in features]
    after, _ = apply_precedence(normalized); eligible = [row for row in after if row["properties"]["elegivel"]]
    inspections = mandatory_inspections(eligible)
    if not args.municipal_sample: raise ValueError("--municipal-sample é obrigatório para concluir o estudo OSRM")
    sample_payload = json.loads(args.municipal_sample.read_text(encoding="utf-8"))
    municipalities = sample_payload.get("municipalities", sample_payload) if isinstance(sample_payload, dict) else sample_payload
    study = osrm_sensitivity_study(eligible, municipalities, OSRMClient(args.osrm_url))
    qa = publish_generation(materialized, args.output, artifacts={"inspecoes.json": inspections, "estudo-osrm.json": study})
    active = json.loads((args.output / "active.json").read_text())
    print(json.dumps({"generation": active["generation"], "coverage": qa["cobertura_publicada"], "study_n": study["n"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
