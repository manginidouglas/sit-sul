#!/usr/bin/env bash
# End-to-end local proof using a bounded extract derived from the frozen Brazil raw.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAW="$ROOT/data/raw/osm/brazil-260801.osm.pbf"
WORK="${ROUTING_SMOKE_WORK:-$ROOT/data/interim/routing/smoke}"
IMAGE='docker://osrm/osrm-backend@sha256:bdfa60e64ae1376bff6ff5605991be50600132a27469a4a9e77c23afd3a6d555'
for tool in osmium skopeo umoci chroot curl; do command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 127; }; done
"$ROOT/scripts/routing/download_osm.sh" "$RAW"
mkdir -p "$WORK"; rm -rf "$WORK/oci" "$WORK/root"
osmium extract -b -49.9,-26.0,-48.8,-25.1 --strategy complete_ways "$RAW" -o "$WORK/curitiba-region-260801.osm.pbf" --overwrite
skopeo copy "$IMAGE" "oci:$WORK/oci:v5.25.0"
umoci unpack --image "$WORK/oci:v5.25.0" "$WORK/root"
mkdir -p "$WORK/root/rootfs/data"; cp "$WORK/curitiba-region-260801.osm.pbf" "$WORK/root/rootfs/data/"
chroot "$WORK/root/rootfs" osrm-extract -p /opt/car.lua /data/curitiba-region-260801.osm.pbf
chroot "$WORK/root/rootfs" osrm-partition /data/curitiba-region-260801.osrm
chroot "$WORK/root/rootfs" osrm-customize /data/curitiba-region-260801.osrm
chroot "$WORK/root/rootfs" osrm-routed --algorithm mld --ip 127.0.0.1 --port 5001 /data/curitiba-region-260801.osrm >"$WORK/routed.log" 2>&1 &
pid=$!; trap 'kill "$pid" 2>/dev/null || true' EXIT
for _ in {1..30}; do curl -fsS 'http://127.0.0.1:5001/route/v1/driving/-49.2679,-25.4133;-49.1758,-25.5285?overview=false' >/dev/null && break; sleep 1; done
PYTHONPATH="$ROOT/src" python - <<'PY'
from ice_sul.routing import Coordinate, OSRMClient
client = OSRMClient("http://127.0.0.1:5001")
origin = Coordinate(-25.4133, -49.2679)
airport = Coordinate(-25.5285, -49.1758)
route = client.route(origin, airport)
matrix = client.table([origin], [airport, origin])
assert route.ok and route.duration_minutes > 0 and route.distance_meters > 0
assert len(matrix.durations_minutes) == 1 and len(matrix.durations_minutes[0]) == 2
print(route); print(matrix)
PY
