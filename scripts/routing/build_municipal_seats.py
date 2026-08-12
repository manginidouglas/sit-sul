#!/usr/bin/env python3
"""Build municipal seats from an immutable official IBGE raw snapshot."""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
import sqlite3
import urllib.request
import zipfile

URL = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip"
SHA256 = "1d96d5f0b379972a506d4b18c3696af974fbe59f8f6680557cb3a6dd38a0eb57"
SIZE = 6_477_540
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/routing/ibge-seats/Localidades_Brasil_gpkg.zip"
CANONICAL = ROOT / "data/processed/2026/municipios.csv"
OUT = ROOT / "data/interim/routing/municipal_seats_south_2022.csv"


def validate_bytes(payload: bytes) -> None:
    if len(payload) != SIZE or hashlib.sha256(payload).hexdigest() != SHA256:
        raise RuntimeError("IBGE raw snapshot size/hash mismatch")


def immutable_raw() -> Path:
    """Reuse a valid raw ZIP, reject an invalid one, or atomically create it."""
    RAW.parent.mkdir(parents=True, exist_ok=True)
    if RAW.exists():
        validate_bytes(RAW.read_bytes())
        return RAW
    part = RAW.with_suffix(RAW.suffix + ".part")
    payload = urllib.request.urlopen(URL, timeout=120).read()  # noqa: S310 - frozen official URL
    validate_bytes(payload)
    part.write_bytes(payload)
    part.replace(RAW)
    return RAW


def canonical_identities() -> dict[str, tuple[str, str]]:
    with CANONICAL.open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    identities = {row["municipio_id"]: (row["municipio_nome"], row["uf_sigla"]) for row in records}
    if len(records) != len(identities):
        raise RuntimeError("duplicate code in canonical municipality snapshot")
    return identities


def validate_against_canonical(rows: list[tuple]) -> None:
    ids = [str(row[0]) for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate municipal seat code")
    actual = {str(row[0]): (str(row[1]), str(row[2])) for row in rows}
    expected = canonical_identities()
    missing, additional = set(expected) - set(actual), set(actual) - set(expected)
    mismatched = {code for code in set(expected) & set(actual) if expected[code] != actual[code]}
    if missing or additional or mismatched:
        raise RuntimeError(
            f"seats differ from canonical municipalities: missing={sorted(missing)}, "
            f"additional={sorted(additional)}, name_or_uf={sorted(mismatched)}"
        )


def main() -> None:
    with zipfile.ZipFile(immutable_raw()) as archive:
        gpkg = ROOT / "data/interim/routing/BR_localidades_2022.gpkg.tmp"
        gpkg.parent.mkdir(parents=True, exist_ok=True)
        gpkg.write_bytes(archive.read("BR_localidades_2022.gpkg"))
    db = sqlite3.connect(gpkg)
    rows = db.execute("""SELECT CD_MUN, NM_MUN, SIGLA_UF, LAT_LOCALIDADE, LONG_LOCALIDADE,
      CASE SCT_LOCALIDADE WHEN 'Capital Federal' THEN 'capital_federal' WHEN 'Capital Estadual' THEN 'capital_estadual' ELSE 'sede_municipal' END
      FROM BR_localidades_2022 WHERE SIGLA_UF IN ('PR','SC','RS') AND CT_LOCALIDADE='Cidade'
      AND SCT_LOCALIDADE IN ('Sede Municipal','Capital Estadual','Capital Federal')
      ORDER BY CD_MUN, CASE WHEN SCT_LOCALIDADE='Sede Municipal' THEN 1 ELSE 0 END""").fetchall()
    db.close()
    gpkg.unlink()
    source_unique = {str(row[0]): row for row in rows}
    identities = canonical_identities()
    unique = [(code, identities.get(code, (row[1], row[2]))[0], identities.get(code, (row[1], row[2]))[1], *row[3:])
              for code, row in source_unique.items()]
    validate_against_canonical(unique)
    with OUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["municipio_id", "municipio_nome", "uf_sigla", "latitude", "longitude", "seat_type"])
        writer.writerows(unique)
    print(f"wrote and canonically validated {len(unique)} seats to {OUT}")


if __name__ == "__main__":
    main()
