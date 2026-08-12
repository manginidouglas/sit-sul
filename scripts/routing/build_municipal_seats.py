#!/usr/bin/env python3
"""Build the versioned municipal-seat CSV from the official IBGE GeoPackage."""
from __future__ import annotations
import csv, hashlib, io, sqlite3, urllib.request, zipfile
from pathlib import Path

URL = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip"
SHA256 = "1d96d5f0b379972a506d4b18c3696af974fbe59f8f6680557cb3a6dd38a0eb57"
SIZE = 6477540
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/interim/routing/municipal_seats_south_2022.csv"


def main() -> None:
    payload = urllib.request.urlopen(URL, timeout=120).read()  # noqa: S310 - frozen official URL
    if len(payload) != SIZE or hashlib.sha256(payload).hexdigest() != SHA256:
        raise RuntimeError("IBGE snapshot size/hash mismatch")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        gpkg = ROOT / "data/interim/routing/BR_localidades_2022.gpkg"
        gpkg.write_bytes(archive.read("BR_localidades_2022.gpkg"))
    db = sqlite3.connect(gpkg)
    rows = db.execute("""SELECT CD_MUN, NM_MUN, SIGLA_UF, LAT_LOCALIDADE, LONG_LOCALIDADE,
      CASE SCT_LOCALIDADE WHEN 'Capital Federal' THEN 'capital_federal' WHEN 'Capital Estadual' THEN 'capital_estadual' ELSE 'sede_municipal' END
      FROM BR_localidades_2022 WHERE SIGLA_UF IN ('PR','SC','RS') AND CT_LOCALIDADE='Cidade'
      AND SCT_LOCALIDADE IN ('Sede Municipal','Capital Estadual','Capital Federal')
      ORDER BY CD_MUN, CASE WHEN SCT_LOCALIDADE='Sede Municipal' THEN 1 ELSE 0 END""").fetchall()
    db.close(); gpkg.unlink()
    unique = {row[0]: row for row in rows}
    if len(unique) != 1191:
        raise RuntimeError(f"expected 1191 unique municipal seats, got {len(unique)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n"); writer.writerow(["municipio_id","municipio_nome","uf_sigla","latitude","longitude","seat_type"])
        writer.writerows(unique.values())
    print(f"wrote {len(unique)} seats to {OUT}")

if __name__ == "__main__": main()
