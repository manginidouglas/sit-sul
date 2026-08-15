#!/usr/bin/env bash
# Reproducibly build or serve the Brazil MLD graph with the pinned OSRM image.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE='osrm/osrm-backend@sha256:bdfa60e64ae1376bff6ff5605991be50600132a27469a4a9e77c23afd3a6d555'
PBF="$ROOT/data/raw/osm/brazil-260801.osm.pbf"
GRAPH="$ROOT/data/interim/routing/osrm"
command -v docker >/dev/null || { echo 'docker is required (Docker Engine 24+)' >&2; exit 127; }
run() { docker run --rm "$@" "$IMAGE"; }
case "${1:-}" in
 build)
  "$ROOT/scripts/routing/download_osm.sh" "$PBF"
  mkdir -p "$GRAPH"; cp "$PBF" "$GRAPH/brazil.osm.pbf"
  run -t -v "$GRAPH:/data" /bin/bash -lc \
    'osrm-extract -p /opt/car.lua /data/brazil.osm.pbf && osrm-partition /data/brazil.osrm && osrm-customize /data/brazil.osrm'
  ;;
 serve)
  [[ -f "$GRAPH/brazil.osrm" ]] || { echo 'run build first' >&2; exit 1; }
  exec docker run --rm --init -p "${OSRM_PORT:-5000}:5000" -v "$GRAPH:/data:ro" "$IMAGE" \
    osrm-routed --algorithm mld --max-table-size "${OSRM_MAX_TABLE_SIZE:-10000}" /data/brazil.osrm
  ;;
 *) echo "usage: $0 {build|serve}" >&2; exit 2;;
esac
