"""Materialização municipal do CNPJ com gates de cobertura e rollback integral."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from ice_sul.extract.cnpj import PARTITIONED, SINGLETONS, validate_topology, validate_zip

SOUTH_UFS = {"PR", "SC", "RS"}
EXPECTED_UF_COUNTS = {"PR": 399, "SC": 295, "RS": 497}
STATE_OWNED_EXCEPTIONS = {"2011", "2038"}
NON_STATE_GROUPS = {"2", "3", "4"}
WIDE_FIELDS = (
    "municipio_id",
    "periodo_referencia",
    "estabelecimentos_ativos_total",
    "estabelecimentos_ativos_mei",
    "estabelecimentos_ativos_sem_mei_identificado",
    "estabelecimentos_ativos_nao_estatais_proxy",
    "estabelecimentos_ativos_nao_estatais_proxy_mei",
    "estabelecimentos_ativos_nao_estatais_proxy_sem_mei_identificado",
    "flag_qualidade",
    "fonte_versao",
)
MEASURE_FIELDS = WIDE_FIELDS[2:8]
ALPHANUMERIC_CNPJ_PART_RE = re.compile(r"[A-Z0-9]+")
LEGAL_NATURE_RE = re.compile(r"(?:\d{4}|\d{3}-\d)")
KNOWN_REGISTRATION_STATUSES = {"1", "01", "2", "02", "3", "03", "4", "04", "8", "08"}
ACTIVE_REGISTRATION_STATUSES = {"2", "02"}
MAX_FAILURE_SAMPLES = 20


class TransformationValidationError(ValueError):
    """Gate substantivo da materialização não foi satisfeito."""


def _rows(path: Path):
    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) != 1:
            raise TransformationValidationError(f"ZIP deve ter um membro: {path}")
        with archive.open(members[0]) as raw:
            with io.TextIOWrapper(raw, encoding="latin-1", newline="") as text:
                yield from csv.reader(text, delimiter=";", quotechar='"')


def _normalized(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_legal_nature(code: str) -> str:
    if LEGAL_NATURE_RE.fullmatch(code) is None:
        raise TransformationValidationError(f"Natureza Jurídica inválida: {code!r}")
    return code.replace("-", "")


def classify_legal_nature(code: str) -> str:
    """Proxy explícita; não pretende identificar todo controle estatal indireto."""
    digits = normalize_legal_nature(code)
    if digits.startswith("1") or digits in STATE_OWNED_EXCEPTIONS:
        return "estatal_identificavel"
    if digits[0] in NON_STATE_GROUPS:
        return "nao_estatal_proxy"
    if digits.startswith("5"):
        return "internacional_extraterritorial"
    raise TransformationValidationError(f"Natureza Jurídica sem regra: {code}")


def validate_manifest(path: Path, snapshot: str) -> tuple[dict[str, Any], dict[str, Path]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("snapshot") != snapshot:
        raise TransformationValidationError("manifesto pertence a outro snapshot")
    if manifest.get("status") != "complete" or manifest.get("coverage_complete") is not True:
        raise TransformationValidationError("manifesto não comprova cobertura completa")
    if (
        manifest.get("source") != "cnpj"
        or not manifest.get("index_url")
        or not manifest.get("license_status")
    ):
        raise TransformationValidationError("manifesto não contém proveniência da fonte")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != manifest.get("expected_artifact_count"):
        raise TransformationValidationError("quantidade de artefatos diverge do manifesto")
    paths: dict[str, Path] = {}
    urls: list[str] = []
    for entry in artifacts:
        if entry.get("snapshot") != snapshot:
            raise TransformationValidationError("artefato mistura snapshots")
        name = entry.get("name")
        if not name or name in paths:
            raise TransformationValidationError("artefato sem nome ou duplicado")
        required_provenance = (
            "source", "url", "method", "parameters", "snapshot",
            "period_reference", "collected_at_utc", "final_url", "http_status",
            "redirects", "content_type", "transferred_bytes", "persisted_bytes",
            "sha256", "logical_path", "license_status", "validated_at_utc",
            "zip_validation", "uncompressed_bytes",
        )
        if any(entry.get(field) in (None, "") for field in required_provenance):
            raise TransformationValidationError(f"proveniência incompleta: {name}")
        if (
            entry["source"] != "cnpj"
            or entry["method"] != "GET"
            or entry["period_reference"] != snapshot
        ):
            raise TransformationValidationError(f"proveniência inconsistente: {name}")
        if entry["http_status"] not in {200, 206}:
            raise TransformationValidationError(f"HTTP inválido no manifesto: {name}")
        raw = Path(entry["path"])
        if not raw.is_file() or raw.stat().st_size != entry.get("persisted_bytes"):
            raise TransformationValidationError(f"tamanho divergente: {raw}")
        if _sha256(raw) != entry.get("sha256"):
            raise TransformationValidationError(f"hash divergente: {raw}")
        validate_zip(raw)
        paths[name] = raw
        urls.append(entry["url"])
    observed = {
        kind: [Path(url).name for url in values]
        for kind, values in validate_topology(urls).items()
    }
    if observed != manifest.get("topology"):
        raise TransformationValidationError("topologia observada diverge da congelada")
    return manifest, paths


def _canonical_universe(path: Path) -> tuple[list[dict[str, str]], dict[tuple[str, str], list[dict[str, str]]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    identifiers = [row["municipio_id"] for row in rows]
    uf_counts = Counter(row["uf_sigla"] for row in rows)
    if (
        len(rows) != 1191
        or len(set(identifiers)) != 1191
        or any(not value.isdigit() or len(value) != 7 for value in identifiers)
        or set(uf_counts) != SOUTH_UFS
        or dict(uf_counts) != EXPECTED_UF_COUNTS
    ):
        raise TransformationValidationError("universo canônico inválido")
    by_name: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_name[(row["uf_sigla"], _normalized(row["municipio_nome"]))].append(row)
    return rows, by_name


def _valid_cnpj_parts(root: str, order: str, dv: str) -> bool:
    """Aceita CNPJ legado e alfanumérico sem coerção numérica."""
    return (
        len(root) == 8
        and ALPHANUMERIC_CNPJ_PART_RE.fullmatch(root) is not None
        and len(order) == 4
        and ALPHANUMERIC_CNPJ_PART_RE.fullmatch(order) is not None
        and len(dv) == 2
        and dv.isascii()
        and dv.isdigit()
    )


def _record_failure(
    failures: dict[str, dict[str, Any]], key: str, value: Any
) -> None:
    item = failures.setdefault(key, {"count": 0, "samples": []})
    item["count"] += 1
    if len(item["samples"]) < MAX_FAILURE_SAMPLES:
        item["samples"].append(value)


def _processing_preflight(
    manifest: dict[str, Any], output_parent: Path
) -> dict[str, Any]:
    establishments = [
        entry
        for entry in manifest["artifacts"]
        if entry["name"].casefold().startswith("estabelecimentos")
    ]
    uncompressed = sum(int(entry["uncompressed_bytes"]) for entry in establishments)
    # A base scratch guarda apenas estabelecimentos ativos do Sul e raízes
    # relacionadas; reserva 20% de todo Estabelecimentos descomprimido para
    # SQLite + WAL/índices, além de 1 GiB para staging/margem.
    incremental_required = int(uncompressed * 0.20) + 1024**3
    free = shutil.disk_usage(output_parent).free
    evidence = {
        "establishments_uncompressed_bytes": uncompressed,
        "persisted_scope": "active establishments in PR/SC/RS and related roots only",
        "sqlite_wal_index_reserve_fraction": 0.20,
        "staging_and_margin_bytes": 1024**3,
        "estimated_incremental_required_bytes": incremental_required,
        "free_bytes_before_processing": free,
        "fits_with_estimated_margin": incremental_required <= free,
    }
    if incremental_required > free:
        raise OSError(
            f"scratch estimado não cabe: {incremental_required} necessários, {free} livres"
        )
    return evidence


def promote_outputs(
    staged: dict[Path, Path],
    *,
    replace: Callable[[Path, Path], Any] = os.replace,
    remove: Callable[[Path], Any] | None = None,
) -> None:
    """Promove conjunto inteiro com journal recuperável após término abrupto."""
    journal = next(iter(staged)).parent / ".cnpj-promotion-journal.json"
    _recover_promotion(journal)
    backups: dict[Path, Path] = {}
    promoted: list[Path] = []
    created_destinations: set[Path] = set()
    token = next(iter(staged.values())).parent.name
    transaction_state = "promoting"
    remove = remove or (lambda path: path.unlink(missing_ok=True))

    def checkpoint() -> None:
        temporary = journal.with_name(journal.name + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "state": transaction_state,
                    "backups": {str(key): str(value) for key, value in backups.items()},
                    "promoted": [str(value) for value in promoted],
                    "created_destinations": [
                        str(value) for value in created_destinations
                    ],
                }
            ),
            encoding="utf-8",
        )
        os.replace(temporary, journal)

    checkpoint()
    try:
        for destination in staged:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.{token}.backup")
                backups[destination] = backup
                checkpoint()
                replace(destination, backup)
            else:
                created_destinations.add(destination)
                checkpoint()
        for destination, source in staged.items():
            replace(source, destination)
            promoted.append(destination)
            checkpoint()
    except Exception:
        for destination in reversed(promoted):
            destination.unlink(missing_ok=True)
        for destination, backup in backups.items():
            if backup.exists():
                os.replace(backup, destination)
        journal.unlink(missing_ok=True)
        raise
    else:
        # O commit precede duravelmente qualquer destruição de backup. Depois
        # deste checkpoint, recovery sempre escolhe a geração nova.
        transaction_state = "committed"
        checkpoint()
        for backup in backups.values():
            remove(backup)
        journal.unlink(missing_ok=True)


def _recover_promotion(journal: Path) -> None:
    if not journal.exists():
        return
    try:
        state = json.loads(journal.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TransformationValidationError(
            f"journal de publicação ilegível: {journal}"
        ) from exc
    promoted = {Path(value) for value in state.get("promoted", [])}
    created = {Path(value) for value in state.get("created_destinations", [])}
    backups = {
        Path(destination): Path(backup)
        for destination, backup in state.get("backups", {}).items()
    }
    if state.get("state") == "committed":
        for backup in backups.values():
            backup.unlink(missing_ok=True)
        journal.unlink()
        return
    for destination in promoted | created:
        destination.unlink(missing_ok=True)
    for destination, backup in backups.items():
        if backup.exists():
            os.replace(backup, destination)
    journal.unlink()


def build_numerators(
    *,
    manifest_path: Path,
    canonical_csv: Path,
    output_csv: Path,
    bridge_csv: Path,
    report_json: Path,
    snapshot: str,
    database: Path | None = None,
    replace: Callable[[Path, Path], Any] = os.replace,
) -> dict[str, Any]:
    # Recovery precisa preceder até mesmo validação/preflight: a nova execução
    # pode falhar antes de alcançar sua própria fase de publicação.
    _recover_promotion(output_csv.parent / ".cnpj-promotion-journal.json")
    manifest, files = validate_manifest(manifest_path, snapshot)
    canonical, canonical_by_name = _canonical_universe(canonical_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    processing_preflight = _processing_preflight(manifest, output_csv.parent)
    staging_root = Path(tempfile.mkdtemp(prefix=".cnpj-staging-", dir=output_csv.parent))
    scratch = database or staging_root / "cnpj.sqlite"
    conn = sqlite3.connect(scratch)
    domains = {"situacao_cadastral": Counter(), "opcao_mei": Counter(), "natureza_juridica": Counter()}
    stats = Counter()
    bridge: dict[tuple[str, str], dict[str, Any]] = {}
    failures: dict[str, dict[str, Any]] = {}
    try:
        conn.executescript(
            "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"
            "CREATE TABLE simples(raiz TEXT PRIMARY KEY, opcao_mei TEXT NOT NULL);"
            "CREATE TABLE empresas(raiz TEXT PRIMARY KEY, natureza TEXT NOT NULL, classe TEXT NOT NULL);"
            "CREATE TABLE active_roots(raiz TEXT PRIMARY KEY);"
            "CREATE TABLE ativos(cnpj TEXT PRIMARY KEY, raiz TEXT NOT NULL, uf TEXT NOT NULL, codigo_rfb TEXT NOT NULL, municipio_id TEXT NOT NULL, payload TEXT NOT NULL);"
        )
        municipal_names: dict[str, str] = {}
        for row in _rows(files["Municipios.zip"]):
            if len(row) < 2 or len(row[0]) != 4 or not row[0].isascii() or not row[0].isdigit():
                raise TransformationValidationError("layout Municipios inesperado")
            if row[0] in municipal_names and municipal_names[row[0]] != row[1]:
                raise TransformationValidationError(f"código RFB municipal conflitante: {row[0]}")
            municipal_names[row[0]] = row[1]

        nature_domain: dict[str, str] = {}
        for row in _rows(files["Naturezas.zip"]):
            if len(row) < 2:
                raise TransformationValidationError("layout Naturezas inesperado")
            code = normalize_legal_nature(row[0])
            if code in nature_domain and nature_domain[code] != row[1]:
                raise TransformationValidationError(f"Natureza duplicada conflitante: {code}")
            nature_domain[code] = row[1]

        for name, path in sorted(files.items()):
            if not name.casefold().startswith("estabelecimentos"):
                continue
            for row in _rows(path):
                if len(row) < 21:
                    raise TransformationValidationError("layout Estabelecimentos inesperado")
                stats["linhas_estabelecimentos"] += 1
                raw_status = row[5]
                domains["situacao_cadastral"][raw_status or "BRANCO"] += 1
                if raw_status not in KNOWN_REGISTRATION_STATUSES:
                    _record_failure(failures, "situacao_cadastral_inesperada", raw_status)
                    continue
                if raw_status not in ACTIVE_REGISTRATION_STATUSES or row[19] not in SOUTH_UFS:
                    continue
                root, order, dv = row[:3]
                if not _valid_cnpj_parts(root, order, dv):
                    _record_failure(
                        failures, "cnpj_estrutura_invalida", [root, order, dv]
                    )
                    continue
                uf, rfb_code = row[19], row[20]
                rfb_name = municipal_names.get(rfb_code)
                if rfb_name is None:
                    _record_failure(failures, "codigo_rfb_ausente", [uf, rfb_code])
                    continue
                normalized_name = _normalized(rfb_name)
                matches = canonical_by_name.get((uf, normalized_name), [])
                if len(matches) != 1:
                    _record_failure(
                        failures,
                        "match_territorial_nao_unico",
                        [uf, rfb_code, rfb_name, len(matches)],
                    )
                    continue
                match = matches[0]
                cnpj = root + order + dv
                payload = json.dumps([root, uf, rfb_code, match["municipio_id"]])
                existing = conn.execute(
                    "SELECT payload FROM ativos WHERE cnpj = ?", (cnpj,)
                ).fetchone()
                if existing:
                    key = "duplicata_exata" if existing[0] == payload else "duplicata_conflitante"
                    stats[key] += 1
                    continue
                conn.execute(
                    "INSERT INTO ativos VALUES (?, ?, ?, ?, ?, ?)",
                    (cnpj, root, uf, rfb_code, match["municipio_id"], payload),
                )
                stats[
                    "cnpj_alfanumerico"
                    if not (root.isascii() and root.isdigit() and order.isascii() and order.isdigit())
                    else "cnpj_numerico"
                ] += 1
                conn.execute("INSERT OR IGNORE INTO active_roots VALUES (?)", (root,))
                bridge[(uf, rfb_code)] = {
                    "uf_observada": uf,
                    "codigo_municipio_rfb": rfb_code,
                    "nome_municipio_rfb": rfb_name,
                    "nome_normalizado": normalized_name,
                    "municipio_id": match["municipio_id"],
                    "municipio_nome_ibge": match["municipio_nome"],
                    "metodo": "codigo_rfb_para_nome_e_nome_normalizado_mais_uf",
                    "justificativa": "correspondencia_unica",
                }
                stats["estabelecimentos_ativos_sul"] += 1

        # Só persiste Simples/Empresas das raízes efetivamente necessárias. Os
        # domínios e linhas nacionais continuam sendo observados durante o scan.
        conn.executescript(
            "CREATE TEMP TABLE stage_simples(raiz TEXT, opcao_mei TEXT);"
            "CREATE TEMP TABLE stage_empresas(raiz TEXT, natureza TEXT, classe TEXT);"
        )
        simples_batch: list[tuple[str, str]] = []

        def flush_simples() -> None:
            if not simples_batch:
                return
            conn.executemany("INSERT INTO stage_simples VALUES (?, ?)", simples_batch)
            try:
                conn.execute(
                    "INSERT INTO simples SELECT s.raiz, s.opcao_mei "
                    "FROM stage_simples s JOIN active_roots a USING(raiz)"
                )
            except sqlite3.IntegrityError as exc:
                raise TransformationValidationError(
                    "raiz ativa duplicada em Simples"
                ) from exc
            conn.execute("DELETE FROM stage_simples")
            simples_batch.clear()

        for row in _rows(files["Simples.zip"]):
            if len(row) < 7:
                raise TransformationValidationError("layout Simples inesperado")
            option = row[4]
            domains["opcao_mei"][option or "BRANCO_OUTROS"] += 1
            stats["linhas_simples_lidas"] += 1
            if option not in {"S", "N", ""}:
                _record_failure(failures, "mei_inesperado", option)
                continue
            simples_batch.append((row[0], option))
            if len(simples_batch) >= 50_000:
                flush_simples()
        flush_simples()

        empresas_batch: list[tuple[str, str, str]] = []

        def flush_empresas() -> None:
            if not empresas_batch:
                return
            conn.executemany("INSERT INTO stage_empresas VALUES (?, ?, ?)", empresas_batch)
            try:
                conn.execute(
                    "INSERT INTO empresas SELECT e.raiz, e.natureza, e.classe "
                    "FROM stage_empresas e JOIN active_roots a USING(raiz)"
                )
            except sqlite3.IntegrityError as exc:
                raise TransformationValidationError(
                    "raiz ativa duplicada em Empresas"
                ) from exc
            conn.execute("DELETE FROM stage_empresas")
            empresas_batch.clear()

        for name, path in sorted(files.items()):
            if not name.casefold().startswith("empresas"):
                continue
            for row in _rows(path):
                if len(row) < 3:
                    raise TransformationValidationError("layout Empresas inesperado")
                nature = normalize_legal_nature(row[2])
                domains["natureza_juridica"][nature] += 1
                stats["linhas_empresas_lidas"] += 1
                if nature not in nature_domain:
                    _record_failure(failures, "natureza_fora_dominio", nature)
                    continue
                empresas_batch.append(
                    (row[0], nature, classify_legal_nature(nature))
                )
                if len(empresas_batch) >= 50_000:
                    flush_empresas()
        flush_empresas()
        stats["raizes_ativas_unicas"] = conn.execute(
            "SELECT COUNT(*) FROM active_roots"
        ).fetchone()[0]
        stats["linhas_simples_persistidas"] = conn.execute(
            "SELECT COUNT(*) FROM simples"
        ).fetchone()[0]
        stats["linhas_empresas_persistidas"] = conn.execute(
            "SELECT COUNT(*) FROM empresas"
        ).fetchone()[0]

        if failures or stats["duplicata_conflitante"]:
            raise TransformationValidationError(
                f"domínios/joins/território inválidos: {dict(failures)}"
            )
        missing_simples = conn.execute(
            "SELECT COUNT(*) FROM ativos a LEFT JOIN simples s USING(raiz) WHERE s.raiz IS NULL"
        ).fetchone()[0]
        missing_empresas = conn.execute(
            "SELECT COUNT(*) FROM ativos a LEFT JOIN empresas e USING(raiz) WHERE e.raiz IS NULL"
        ).fetchone()[0]
        if missing_simples or missing_empresas:
            raise TransformationValidationError(
                f"raízes ativas sem join: Simples={missing_simples}, Empresas={missing_empresas}"
            )
        counts = {
            row[0]: tuple(int(value) for value in row[1:])
            for row in conn.execute(
                """
                SELECT municipio_id,
                       COUNT(*),
                       SUM(opcao_mei = 'S'),
                       SUM(opcao_mei <> 'S'),
                       SUM(classe = 'nao_estatal_proxy'),
                       SUM(classe = 'nao_estatal_proxy' AND opcao_mei = 'S'),
                       SUM(classe = 'nao_estatal_proxy' AND opcao_mei <> 'S')
                FROM ativos JOIN simples USING(raiz) JOIN empresas USING(raiz)
                GROUP BY municipio_id
                """
            )
        }
        bridge_counts = dict(
            conn.execute(
                "SELECT uf || ':' || codigo_rfb, COUNT(*) FROM ativos GROUP BY uf, codigo_rfb"
            )
        )
        staged_wide = staging_root / "municipios.csv"
        staged_bridge = staging_root / "bridge.csv"
        staged_qa = staging_root / "qa.json"
        with staged_wide.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=WIDE_FIELDS)
            writer.writeheader()
            for municipality in canonical:
                values = counts.get(municipality["municipio_id"], (0, 0, 0, 0, 0, 0))
                writer.writerow(
                    dict(
                        zip(
                            WIDE_FIELDS,
                            (
                                municipality["municipio_id"],
                                snapshot,
                                *values,
                                "observado" if values[0] else "zero_observado",
                                f"RFB-CNPJ-{snapshot}",
                            ),
                            strict=True,
                        )
                    )
                )
        bridge_fields = [
            "uf_observada", "codigo_municipio_rfb", "nome_municipio_rfb",
            "nome_normalizado", "municipio_id", "municipio_nome_ibge", "metodo",
            "justificativa", "estabelecimentos_ativos",
        ]
        with staged_bridge.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=bridge_fields)
            writer.writeheader()
            for key, item in sorted(bridge.items()):
                writer.writerow(
                    {**item, "estabelecimentos_ativos": bridge_counts[f"{key[0]}:{key[1]}"]}
                )
        totals = [sum(values[index] for values in counts.values()) for index in range(6)]
        state_components = {
            row[0]: {
                "total": int(row[1]),
                "mei": int(row[2]),
                "sem_mei_identificado": int(row[3]),
                "nao_estatal_proxy": int(row[4]),
                "nao_estatal_proxy_mei": int(row[5]),
                "nao_estatal_proxy_sem_mei_identificado": int(row[6]),
            }
            for row in conn.execute(
                """
                SELECT uf, COUNT(*), SUM(opcao_mei = 'S'), SUM(opcao_mei <> 'S'),
                       SUM(classe = 'nao_estatal_proxy'),
                       SUM(classe = 'nao_estatal_proxy' AND opcao_mei = 'S'),
                       SUM(classe = 'nao_estatal_proxy' AND opcao_mei <> 'S')
                FROM ativos JOIN simples USING(raiz) JOIN empresas USING(raiz)
                GROUP BY uf
                """
            )
        }
        for uf in SOUTH_UFS:
            state_components.setdefault(
                uf,
                {
                    "total": 0, "mei": 0, "sem_mei_identificado": 0,
                    "nao_estatal_proxy": 0, "nao_estatal_proxy_mei": 0,
                    "nao_estatal_proxy_sem_mei_identificado": 0,
                },
            )

        def diagnostic(municipality: dict[str, str]) -> dict[str, Any]:
            values = counts.get(municipality["municipio_id"], (0, 0, 0, 0, 0, 0))
            return {
                "municipio_id": municipality["municipio_id"],
                "municipio_nome": municipality["municipio_nome"],
                "uf": municipality["uf_sigla"],
                **dict(zip(MEASURE_FIELDS, values, strict=True)),
                "mei_share": values[1] / values[0] if values[0] else None,
                "non_state_proxy_share": values[3] / values[0] if values[0] else None,
            }

        sanity: dict[str, Any] = {"capitals": [], "by_uf": {}}
        capitals = {"CURITIBA", "FLORIANOPOLIS", "PORTO ALEGRE"}
        sanity["capitals"] = [
            diagnostic(item)
            for item in canonical
            if _normalized(item["municipio_nome"]) in capitals
        ]
        for uf in sorted(SOUTH_UFS):
            members = [item for item in canonical if item["uf_sigla"] == uf]
            ordered = sorted(
                members,
                key=lambda item: counts.get(item["municipio_id"], (0,))[0],
            )
            nonzero = [item for item in ordered if counts.get(item["municipio_id"], (0,))[0] > 0]
            sanity["by_uf"][uf] = {
                "zero_count": len(ordered) - len(nonzero),
                "lowest_nonzero": [diagnostic(item) for item in nonzero[:5]],
                "highest": [diagnostic(item) for item in reversed(ordered[-5:])],
            }
        quality = {
            "status": "approved",
            "snapshot": snapshot,
            "coverage_complete": manifest["coverage_complete"],
            "processing_preflight": processing_preflight,
            "topology": manifest["topology"],
            "parts": {kind: len(manifest["topology"][kind]) for kind in (*PARTITIONED, *SINGLETONS)},
            "rows_read": dict(stats),
            "domains_observed": {name: dict(counter) for name, counter in domains.items()},
            "joins": {"active_roots_without_simples": missing_simples, "active_roots_without_empresa": missing_empresas},
            "territorialization": {"observed_pairs": len(bridge), "unmatched_pairs": 0},
            "municipal_universe": {"rows": len(canonical), "unique_ids": len({row['municipio_id'] for row in canonical}), "uf_counts": EXPECTED_UF_COUNTS},
            "totals": {
                "sul": totals[0], "mei": totals[1], "sem_mei_identificado": totals[2],
                "nao_estatal_proxy": totals[3], "nao_estatal_proxy_mei": totals[4],
                "nao_estatal_proxy_sem_mei_identificado": totals[5],
                "by_uf": state_components,
            },
            "sanity_checks": sanity,
            "duplicates": {"exact": stats["duplicata_exata"], "conflicting": stats["duplicata_conflitante"]},
            "gates": {
                "snapshot_complete": True,
                "universe_exact": True,
                "territorialization_complete": True,
                "joins_complete": True,
                "total_equals_mei_plus_without_identified_mei": totals[0] == totals[1] + totals[2],
                "proxy_equals_mei_plus_without_identified_mei": totals[3] == totals[4] + totals[5],
                "municipal_sum_equals_south": sum(value[0] for value in counts.values()) == totals[0],
                "state_sum_equals_south": sum(
                    values["total"] for values in state_components.values()
                ) == totals[0],
            },
        }
        if not all(quality["gates"].values()):
            raise TransformationValidationError("reconciliação final falhou")
        staged_qa.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        promote_outputs(
            {
                output_csv: staged_wide,
                bridge_csv: staged_bridge,
                report_json: staged_qa,
            },
            replace=replace,
        )
        return quality
    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(scratch) + suffix).unlink(missing_ok=True)
        shutil.rmtree(staging_root, ignore_errors=True)
