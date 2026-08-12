#!/usr/bin/env bash
# Download a frozen OSM input without ever replacing an existing raw artifact.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/data/raw/osm/brazil-260801.osm.pbf}"
URL="${OSM_SNAPSHOT_URL:-https://download.geofabrik.de/south-america/brazil-260801.osm.pbf}"
EXPECTED_MD5="${OSM_SNAPSHOT_MD5:-265d58e0eb10236a28b64fe846c92925}"
EXPECTED_SHA256="${OSM_SNAPSHOT_SHA256:-2b2ae9d8eb9a2d27501e4ab3a7097cab904439cbc7627319e5a4ce070dba27fd}"
EXPECTED_SIZE="${OSM_SNAPSHOT_SIZE:-2066032748}"
verify() {
  [[ "$(stat -c %s "$1")" == "$EXPECTED_SIZE" ]] &&
    echo "$EXPECTED_MD5  $1" | md5sum --check --status &&
    echo "$EXPECTED_SHA256  $1" | sha256sum --check --status
}
mkdir -p "$(dirname "$OUT")"
if [[ -e "$OUT" ]]; then
  verify "$OUT" && { echo "verified existing immutable raw $OUT"; exit 0; }
  echo "refusing to replace existing immutable raw with unexpected size/checksum: $OUT" >&2
  exit 1
fi
PART="$OUT.part"
if [[ -e "$PART" ]] && ! verify "$PART"; then rm -f "$PART"; fi
if [[ ! -e "$PART" ]]; then
  curl --fail --location --retry 5 --output "$PART" "$URL"
fi
verify "$PART" || { echo "downloaded .part has unexpected size/checksum" >&2; exit 1; }
mv "$PART" "$OUT"
echo "downloaded, validated, and promoted $OUT"
