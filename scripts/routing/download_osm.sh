#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/data/raw/osm/brazil-260801.osm.pbf}"
URL=https://download.geofabrik.de/south-america/brazil-260801.osm.pbf
EXPECTED_MD5=265d58e0eb10236a28b64fe846c92925
EXPECTED_SIZE=2066032748
mkdir -p "$(dirname "$OUT")"
if [[ -f "$OUT" ]] && [[ "$(stat -c %s "$OUT")" == "$EXPECTED_SIZE" ]] && echo "$EXPECTED_MD5  $OUT" | md5sum --check --status; then
  echo "verified existing $OUT"; exit 0
fi
curl --fail --location --continue-at - --retry 5 --output "$OUT.part" "$URL"
[[ "$(stat -c %s "$OUT.part")" == "$EXPECTED_SIZE" ]] || { echo "unexpected byte size" >&2; exit 1; }
echo "$EXPECTED_MD5  $OUT.part" | md5sum --check --status || { echo "MD5 mismatch" >&2; exit 1; }
mv "$OUT.part" "$OUT"
echo "downloaded and verified $OUT"
