"""Extração e validação do cadastro canônico de municípios do IBGE.

O módulo usa apenas a biblioteca padrão para que a primeira entrega possa ser
reproduzida em um ambiente Python limpo. Respostas brutas nunca são alteradas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen

UFS = {"PR": "41", "SC": "42", "RS": "43"}
FIELDS = (
    "municipio_id", "municipio_nome", "uf_sigla", "uf_codigo",
    "regiao_nome", "mesorregiao", "microrregiao",
    "regiao_intermediaria", "regiao_imediata", "vigencia_inicio",
    "vigencia_fim", "ativo_edicao",
)


class ValidationError(ValueError):
    """Indica que o cadastro não pode ser publicado."""


@dataclass(frozen=True)
class Download:
    uf: str
    url: str
    body: bytes
    extracted_at: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def fetch(url: str, uf: str, timeout: int = 60) -> Download:
    request = Request(url, headers={"User-Agent": "ice-sul/0.1 (+cadastro-municipal)"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"IBGE retornou HTTP {response.status} para {uf}")
        body = response.read()
    return Download(uf, url, body, datetime.now(UTC).isoformat())


def _name(value: dict[str, Any] | None) -> str:
    return "" if not value else str(value.get("nome", ""))


def normalize(item: dict[str, Any], *, vigencia_inicio: str) -> dict[str, str]:
    imediata = item.get("regiao-imediata") or {}
    intermediaria = imediata.get("regiao-intermediaria") or {}
    uf = ((intermediaria.get("UF") or {}))
    regiao = uf.get("regiao") or {}
    micro = item.get("microrregiao") or {}
    meso = micro.get("mesorregiao") or {}
    # A API ocasionalmente omite a UF na árvore vigente, mas a mantém na legada.
    uf = uf or (meso.get("UF") or {})
    return {
        "municipio_id": str(item.get("id", "")),
        "municipio_nome": str(item.get("nome", "")),
        "uf_sigla": str(uf.get("sigla", "")),
        "uf_codigo": str(uf.get("id", "")),
        "regiao_nome": _name(regiao or uf.get("regiao")),
        "mesorregiao": _name(meso),
        "microrregiao": _name(micro),
        "regiao_intermediaria": _name(intermediaria),
        "regiao_imediata": _name(imediata),
        "vigencia_inicio": vigencia_inicio,
        "vigencia_fim": "",
        "ativo_edicao": "true",
    }


def validate(rows: Iterable[dict[str, str]], expected_counts: dict[str, int]) -> dict[str, Any]:
    rows = list(rows)
    errors: list[str] = []
    ids = [row["municipio_id"] for row in rows]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"códigos duplicados: {', '.join(duplicate_ids)}")
    for index, row in enumerate(rows, 2):
        missing = [field for field in FIELDS if field not in {"mesorregiao", "microrregiao", "vigencia_fim"} and not row.get(field)]
        if missing:
            errors.append(f"linha {index}: campos obrigatórios vazios: {', '.join(missing)}")
        if len(row.get("municipio_id", "")) != 7 or not row.get("municipio_id", "").isdigit():
            errors.append(f"linha {index}: municipio_id deve ter sete dígitos")
        uf = row.get("uf_sigla", "")
        if uf not in UFS or row.get("uf_codigo") != UFS.get(uf):
            errors.append(f"linha {index}: UF/código fora do universo")
    actual = Counter(row["uf_sigla"] for row in rows)
    for uf, expected in expected_counts.items():
        if actual[uf] != expected:
            errors.append(f"{uf}: fonte contém {expected}, cadastro contém {actual[uf]}")
    report = {
        "status": "reprovado" if errors else "aprovado",
        "total": len(rows),
        "contagens_por_uf": dict(sorted(actual.items())),
        "contagens_esperadas_da_fonte": expected_counts,
        "codigos_unicos": len(set(ids)),
        "erros": errors,
    }
    if errors:
        raise ValidationError("; ".join(errors))
    return report


def build(*, edition: str, cutoff: str, valid_from: str, url_template: str, root: Path) -> tuple[Path, Path]:
    raw_dir = root / "data" / "raw" / "ibge_localidades" / cutoff
    output_dir = root / "data" / "processed" / edition
    report_dir = root / "reports" / "quality" / edition
    for directory in (raw_dir, output_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    expected: dict[str, int] = {}
    manifest: list[dict[str, Any]] = []
    for uf in UFS:
        url = url_template.format(uf=uf)
        download = fetch(url, uf)
        raw_path = raw_dir / f"municipios_{uf}.json"
        raw_path.write_bytes(download.body)
        payload = json.loads(download.body)
        if not isinstance(payload, list):
            raise ValidationError(f"resposta do IBGE para {uf} não é uma lista")
        expected[uf] = len(payload)  # nunca fixa totais como verdade no código
        rows.extend(normalize(item, vigencia_inicio=valid_from) for item in payload)
        manifest.append({"uf": uf, "url": url, "extraido_em": download.extracted_at,
                         "http_status": 200, "bytes": len(download.body), "sha256": download.sha256})
    rows.sort(key=lambda row: row["municipio_id"])
    report = validate(rows, expected)
    csv_path = output_dir / "municipios.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report.update({"edicao": edition, "data_corte": cutoff, "fonte": "API de Localidades do IBGE", "manifesto": manifest})
    report_path = report_dir / "municipios.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, report_path


def _config(path: Path) -> dict[str, str]:
    """Lê o subconjunto escalar do YAML da edição, sem dependência externa."""
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrói o cadastro municipal canônico")
    parser.add_argument("--config", type=Path, default=Path("config/edicoes/2026.yml"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    config = _config(args.config)
    try:
        csv_path, report_path = build(edition=config["edicao"], cutoff=config["data_corte"],
            valid_from=config["vigencia_inicio"], url_template=config["fonte_municipios"], root=args.root)
    except (OSError, RuntimeError, ValidationError, json.JSONDecodeError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(csv_path)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
