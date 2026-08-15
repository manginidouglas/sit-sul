"""Materializa o universo ANTAQ 2025: ``python -m ice_sul.transform.antaq_materialize``."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .antaq import evaluate_annual_installations, read_antaq_installations, read_antaq_movements

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/antaq"
INTERIM = ROOT / "data/interim/antaq"
REPORT = ROOT / "reports/quality/mvp-demo-2026/antaq"
MANIFEST = REPORT / "manifesto.json"
UNIVERSE = INTERIM / "instalacoes_portuarias_avaliadas_2025.csv"
ELIGIBLE = INTERIM / "instalacoes_elegiveis_2025.csv"
QA = REPORT / "qa.json"
MANUAL_IDS = ["BRPNG", "BRANT", "BRSFS", "BRITJ", "BRSC008", "BRIBB", "BRRIG"]


def _validate_manifest() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for artifact in manifest["artefatos"]:
        path = ROOT / artifact["arquivo"]
        if not path.is_file():
            raise FileNotFoundError(f"raw esperado ausente: {path}")
        payload = path.read_bytes()
        if len(payload) != artifact["tamanho"]:
            raise ValueError(f"tamanho diverge do manifesto: {path}")
        if hashlib.sha256(payload).hexdigest() != artifact["sha256"]:
            raise ValueError(f"SHA-256 diverge do manifesto: {path}")
    return manifest


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("saída vazia")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def materialize() -> dict:
    manifest = _validate_manifest()
    installations = read_antaq_installations(RAW / "instalacoes-portuarias-2025-05-06.zip")
    evidence = read_antaq_movements(RAW / "anuario-2025-evidencias.tsv")
    evaluated = evaluate_annual_installations(installations, evidence)
    _write_csv(UNIVERSE, evaluated)
    eligible = [row for row in evaluated if row["status_mvp"] == "elegivel"]
    _write_csv(ELIGIBLE, eligible)

    type_counts = Counter(row["categoria_mvp"] for row in evaluated)
    status_counts = Counter(row["status_mvp"] for row in evaluated)
    by_type = {}
    for category in ("porto_organizado", "tup"):
        counts = Counter(row["status_mvp"] for row in evaluated if row["categoria_mvp"] == category)
        by_type[category] = {key: counts[key] for key in ("elegivel", "nao_elegivel", "indeterminado")}
    ids = Counter(row["instalacao_uid"] for row in evaluated)
    invalid = [row["instalacao_uid"] for row in evaluated if row["latitude"] and row["longitude"] and not row["coordenada_valida"]]
    missing = [row["instalacao_uid"] for row in evaluated if not row["latitude"] or not row["longitude"]]
    unknown_types = sorted({str(row["tipo_oficial"]) for row in evaluated if row["categoria_mvp"] == "fora_escopo_mvp"})
    manual = []
    for identifier in MANUAL_IDS:
        row = next((item for item in evaluated if item["instalacao_id_antaq"] == identifier), None)
        if row is None:
            raise ValueError(f"caso manual ausente do cadastro: {identifier}")
        manual.append({key: row[key] for key in (
            "instalacao_uid", "instalacao_id_antaq", "nome", "tipo_oficial", "status_mvp", "justificativa_status",
            "movimentacao_evidenciada_t", "escopo_movimentacao_evidenciada",
            "fonte_movimentacao", "pagina_ou_referencia", "periodo_inicio", "periodo_fim",
            "latitude", "longitude", "coordenada_valida", "ajuste_acesso_terrestre_onda2",
        )})
    qa = {
        "universo_cadastral": {
            "total": len(evaluated), "porto_organizado": type_counts["porto_organizado"],
            "tup": type_counts["tup"], "outras_categorias": type_counts["fora_escopo_mvp"],
            "coordenadas_validas": len(evaluated) - len(missing) - len(invalid),
            "sem_coordenadas": len(missing),
        },
        "status_mvp": {key: status_counts[key] for key in ("elegivel", "nao_elegivel", "indeterminado", "fora_escopo_mvp")},
        "por_tipo": by_type,
        "evidencias": {
            "instalacoes_com_evidencia": len({row["instalacao_id"] for row in evidence}),
            "sem_evidencia_suficiente": status_counts["indeterminado"],
            "fontes": sorted({row["fonte_movimentacao"] for row in evidence}),
            "periodo": "2025-01-01/2025-12-31",
        },
        "coordenadas": {
            "validas": sum(bool(row["coordenada_valida"]) for row in evaluated),
            "invalidas_ou_ausentes": sum(not bool(row["coordenada_valida"]) for row in evaluated),
            "ajuste_acesso_terrestre_onda2_true": sum(bool(row["ajuste_acesso_terrestre_onda2"]) for row in evaluated),
            "ajuste_acesso_terrestre_onda2_false": sum(not bool(row["ajuste_acesso_terrestre_onda2"]) for row in evaluated),
            "ausentes": len(missing),
        },
        "inconsistencias": {
            "n_linhas_cadastro": len(evaluated),
            "n_instalacao_id_antaq_distintos": len({row["instalacao_id_antaq"] for row in evaluated}),
            "n_instalacao_uid_distintos": len({row["instalacao_uid"] for row in evaluated}),
            "ids_conflitantes": sorted({row["instalacao_id_antaq"] for row in evaluated if row["conflito_cadastral"]}),
            "solucao_bram021": "dois UIDs determinísticos por tipo; ambas as linhas bloqueadas para elegibilidade e routing",
            "duplicidades_uid": {key: value for key, value in ids.items() if value > 1},
            "ids_vazios": sum(not row["instalacao_uid"] for row in evaluated),
            "coordenadas_invalidas": invalid,
            "categorias_desconhecidas_fora_escopo": unknown_types,
            "evidencia_sem_cadastro": [],
        },
        "casos_manuais": manual,
        "encoding_replacement_char_count": sum(str(value).count("�") for row in evaluated for value in row.values()),
        "artefatos_manifestados": len(manifest["artefatos"]),
    }
    if any("�" in str(value) for row in evaluated for value in row.values()):
        raise ValueError("output contém caractere de substituição U+FFFD")
    if len({row["instalacao_uid"] for row in evaluated}) != len(evaluated):
        raise ValueError("instalacao_uid duplicado")
    QA.parent.mkdir(parents=True, exist_ok=True)
    QA.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return qa


def main() -> None:
    qa = materialize()
    print(json.dumps({"output": str(UNIVERSE.relative_to(ROOT)), "status_mvp": qa["status_mvp"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
