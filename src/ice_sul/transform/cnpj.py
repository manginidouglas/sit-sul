"""Agrega estabelecimentos ativos do CNPJ em disco, com e sem MEI."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

ACTIVE_STATUS = "02"  # leiaute oficial: situação cadastral ATIVA
SOUTH_UFS = {"PR", "SC", "RS"}
OUTPUT_FIELDS = ("municipio_id", "estabelecimentos_ativos_com_mei",
                 "estabelecimentos_ativos_sem_mei", "estabelecimentos_ativos_mei")


def _rows(path: Path):
    """Itera diretamente no primeiro membro do ZIP; nunca descompacta ou materializa."""
    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) != 1:
            raise ValueError(f"ZIP deve conter exatamente um arquivo: {path}")
        with archive.open(members[0]) as raw:
            import io
            with io.TextIOWrapper(raw, encoding="latin-1", newline="") as text:
                yield from csv.reader(text, delimiter=";", quotechar='"')


def _normalized(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


def municipality_bridge(municipios_zip: Path, canonical_csv: Path) -> dict[tuple[str, str], str]:
    canonical: dict[tuple[str, str], list[str]] = {}
    with canonical_csv.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            canonical.setdefault((row["uf_sigla"], _normalized(row["municipio_nome"])), []).append(row["municipio_id"])
    official = {row[0]: _normalized(row[1]) for row in _rows(municipios_zip) if len(row) >= 2}
    bridge = {}
    for uf in SOUTH_UFS:
        for rfb_code, name in official.items():
            matches = canonical.get((uf, name), [])
            if len(matches) == 1:
                bridge[(uf, rfb_code)] = matches[0]
    return bridge


def build_numerators(*, establishments: list[Path], simples_zip: Path,
                     municipios_zip: Path, canonical_csv: Path, output_csv: Path,
                     report_json: Path, snapshot: str, database: Path | None = None) -> dict:
    """Usa SQLite temporário para que custo de RAM não cresça com o snapshot."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    database = database or output_csv.with_suffix(".sqlite")
    if database.exists():
        database.unlink()
    bridge = municipality_bridge(municipios_zip, canonical_csv)
    conn = sqlite3.connect(database)
    try:
        conn.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; "
            "CREATE TABLE mei(raiz TEXT PRIMARY KEY); "
            "CREATE TABLE active(cnpj TEXT PRIMARY KEY, municipio_id TEXT NOT NULL, raiz TEXT NOT NULL);")
        mei_read = 0
        batch = []
        for row in _rows(simples_zip):
            if len(row) < 6:
                raise ValueError("linha Simples incompatível com leiaute oficial")
            mei_read += 1
            if row[4].strip().upper() == "S":  # opção pelo MEI, campo oficial
                batch.append((row[0],))
            if len(batch) >= 50_000:
                conn.executemany("INSERT OR IGNORE INTO mei VALUES (?)", batch); batch.clear()
        conn.executemany("INSERT OR IGNORE INTO mei VALUES (?)", batch)
        stats = Counter(); unknown = Counter(); batch = []
        for path in establishments:
            for row in _rows(path):
                stats["linhas_estabelecimentos"] += 1
                if len(row) < 21:
                    raise ValueError("linha Estabelecimentos incompatível com leiaute oficial")
                if row[5] != ACTIVE_STATUS or row[19] not in SOUTH_UFS:
                    continue
                municipio_id = bridge.get((row[19], row[20]))
                if not municipio_id:
                    unknown[(row[19], row[20])] += 1
                    continue
                cnpj = row[0] + row[1] + row[2]
                batch.append((cnpj, municipio_id, row[0]))
                if len(batch) >= 50_000:
                    before = conn.total_changes
                    conn.executemany("INSERT OR IGNORE INTO active VALUES (?,?,?)", batch)
                    stats["duplicados"] += len(batch) - (conn.total_changes - before); batch.clear()
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO active VALUES (?,?,?)", batch)
        stats["duplicados"] += len(batch) - (conn.total_changes - before)
        conn.commit()
        counts = {row[0]: row[1:] for row in conn.execute("""
          SELECT municipio_id, COUNT(*), SUM(CASE WHEN mei.raiz IS NULL THEN 1 ELSE 0 END),
                 SUM(CASE WHEN mei.raiz IS NOT NULL THEN 1 ELSE 0 END)
          FROM active LEFT JOIN mei USING (raiz) GROUP BY municipio_id""")}
        with canonical_csv.open(encoding="utf-8", newline="") as source, output_csv.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=OUTPUT_FIELDS); writer.writeheader()
            for row in csv.DictReader(source):
                total, without, mei = counts.get(row["municipio_id"], (0, 0, 0))
                writer.writerow(dict(zip(OUTPUT_FIELDS, (row["municipio_id"], total, without, mei))))
        active_total = conn.execute("SELECT COUNT(*) FROM active").fetchone()[0]
        mei_total = conn.execute("SELECT COUNT(*) FROM mei").fetchone()[0]
    finally:
        conn.close()
    report = {"status": "aprovado" if not unknown else "reprovado", "snapshot": snapshot,
      "situacao_ativa_codigo": ACTIVE_STATUS, "unidade": "estabelecimento (CNPJ completo)",
      "regra_mei": "campo OPÇÃO PELO MEI = S no arquivo Simples, ligado por CNPJ básico",
      "ufs": sorted(SOUTH_UFS), "linhas_simples": mei_read, "raizes_mei": mei_total,
      "linhas_estabelecimentos": stats["linhas_estabelecimentos"], "estabelecimentos_ativos_sul": active_total,
      "duplicados_cnpj_descartados": stats["duplicados"], "codigos_municipais_nao_mapeados":
      [{"uf": key[0], "codigo_rfb": key[1], "linhas": value} for key, value in sorted(unknown.items())],
      "recursos": "ZIP lido em streaming; lotes de 50.000; junção/indexação em SQLite em disco"}
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if unknown:
        raise ValueError("há estabelecimentos ativos com código municipal não mapeado; consulte o relatório")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Constrói numeradores municipais do CNPJ")
    p.add_argument("--estabelecimentos", type=Path, nargs="+", required=True)
    p.add_argument("--simples", type=Path, required=True); p.add_argument("--municipios", type=Path, required=True)
    p.add_argument("--canonical", type=Path, default=Path("data/processed/2026/municipios.csv"))
    p.add_argument("--snapshot", required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True); a = p.parse_args(argv)
    build_numerators(establishments=a.estabelecimentos, simples_zip=a.simples,
      municipios_zip=a.municipios, canonical_csv=a.canonical, output_csv=a.output,
      report_json=a.report, snapshot=a.snapshot)
    return 0


if __name__ == "__main__": raise SystemExit(main())
