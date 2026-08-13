#!/usr/bin/env bash
# End-to-end local proof using a bounded extract derived from the frozen Brazil raw.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAW="$ROOT/data/raw/osm/brazil-260801.osm.pbf"
WORK="${ROUTING_SMOKE_WORK:-$ROOT/data/interim/routing/smoke}"
REPORT="${ROUTING_SMOKE_REPORT:-$ROOT/reports/quality/mvp-demo-2026/routing/local-smoke-results.json}"
IMAGE='docker://osrm/osrm-backend@sha256:bdfa60e64ae1376bff6ff5605991be50600132a27469a4a9e77c23afd3a6d555'
BBOX='-49.9,-26.0,-48.8,-25.1'
for tool in osmium skopeo umoci chroot curl /usr/bin/time; do command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 127; }; done
"$ROOT/scripts/routing/download_osm.sh" "$RAW"
mkdir -p "$WORK"; rm -rf "$WORK/oci" "$WORK/root"
osmium extract -b "$BBOX" --strategy complete_ways "$RAW" -o "$WORK/curitiba-region-260801.osm.pbf" --overwrite
skopeo copy "$IMAGE" "oci:$WORK/oci:v5.25.0"
umoci unpack --image "$WORK/oci:v5.25.0" "$WORK/root"
mkdir -p "$WORK/root/rootfs/data"; cp "$WORK/curitiba-region-260801.osm.pbf" "$WORK/root/rootfs/data/"
measure() { local stage="$1"; shift; /usr/bin/time -f '%e %M' -o "$WORK/$stage.metrics" "$@"; }
measure extract chroot "$WORK/root/rootfs" osrm-extract -p /opt/car.lua /data/curitiba-region-260801.osm.pbf
measure partition chroot "$WORK/root/rootfs" osrm-partition /data/curitiba-region-260801.osrm
measure customize chroot "$WORK/root/rootfs" osrm-customize /data/curitiba-region-260801.osrm
serve_started="$(date +%s%N)"
chroot "$WORK/root/rootfs" osrm-routed --algorithm mld --ip 127.0.0.1 --port 5001 /data/curitiba-region-260801.osrm >"$WORK/routed.log" 2>&1 &
pid=$!; trap 'kill "$pid" 2>/dev/null || true' EXIT
ready=0
for _ in {1..30}; do
  if curl -fsS 'http://127.0.0.1:5001/route/v1/driving/-49.2679,-25.4133;-49.1758,-25.5285?overview=false' >/dev/null; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'osrm-routed did not become ready' >&2; exit 1; }
serve_ready="$(date +%s%N)"
export ROOT WORK REPORT BBOX serve_started serve_ready
PYTHONPATH="$ROOT/src" python - <<'PY'
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from ice_sul.routing import Coordinate, OSRMClient

root, work = Path(os.environ["ROOT"]), Path(os.environ["WORK"])
client = OSRMClient("http://127.0.0.1:5001")
# Both origins and destinations are inside the controlled Curitiba/Lapa extract.
sources = [
    Coordinate(-25.4133, -49.2679),  # Curitiba IBGE seat
    Coordinate(-25.7698, -49.7158),  # Lapa IBGE seat
]
destinations = [
    Coordinate(-25.5285, -49.1758),  # Afonso Pena sanity coordinate
    Coordinate(-25.4133, -49.2679),  # Curitiba IBGE seat
]
route = client.route(sources[0], destinations[0])
matrix = client.table(sources, destinations)
assert route.ok and route.duration_minutes > 0 and route.distance_meters > 0
assert len(matrix.durations_minutes) == 2
assert all(len(row) == 2 for row in matrix.durations_minutes)
assert matrix.distances_meters is not None and len(matrix.distances_meters) == 2
assert all(len(row) == 2 for row in matrix.distances_meters)

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def stage(name: str) -> dict:
    elapsed, rss = (work / f"{name}.metrics").read_text().split()
    return {"status": "success", "elapsed_seconds": float(elapsed), "max_rss_kib": int(rss)}

snapshot = json.loads((root / "data/raw/osm/snapshot.json").read_text())
extract = work / "curitiba-region-260801.osm.pbf"
osrm_version = subprocess.run(
    ["chroot", str(work / "root/rootfs"), "osrm-routed", "--version"],
    check=True, capture_output=True, text=True,
).stdout.strip().lstrip("v")
route_payload = asdict(route)
route_payload["code"] = "Ok"
route_payload["from"] = "Curitiba IBGE seat"
route_payload["to"] = "Afonso Pena sanity coordinate"
table_payload = asdict(matrix)
table_payload.update({
    "code": "Ok", "sources": len(sources), "destinations": len(destinations),
    "source_names": ["Curitiba IBGE seat", "Lapa IBGE seat"],
    "destination_names": ["Afonso Pena sanity coordinate", "Curitiba IBGE seat"],
})
report = {
    "executed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "method": "OSRM official OCI image unpacked with skopeo/umoci and executed locally with chroot",
    "osrm_version": osrm_version,
    "profile": "car.lua",
    "algorithm": "MLD",
    "source_snapshot": snapshot["path"],
    "source_sha256": digest(root / snapshot["path"]),
    "smoke_extract": {
        "bbox": [float(value) for value in os.environ["BBOX"].split(",")],
        "size_bytes": extract.stat().st_size,
        "sha256": digest(extract),
    },
    "stages": {
        "extract": stage("extract"), "partition": stage("partition"),
        "customize": stage("customize"),
        "serve": {
            "status": "success", "listen": "127.0.0.1:5001",
            "startup_seconds": (int(os.environ["serve_ready"]) - int(os.environ["serve_started"])) / 1e9,
        },
    },
    "route": route_payload,
    "table": table_payload,
}
report_path = Path(os.environ["REPORT"])
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(f"wrote reproducible smoke evidence to {report_path}")
PY
