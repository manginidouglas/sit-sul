#!/usr/bin/env python3
"""Preflight reproduzível da API de controle usando apenas a biblioteca padrão."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/PR/municipios"


def validate_pr_payload(body: bytes) -> list[dict]:
    """Rejeita HTML/erros 200 e confirma o universo corrente de 399 municípios."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("resposta não é JSON válido") from exc
    if not isinstance(payload, list) or len(payload) != 399:
        raise ValueError("resposta deve ser uma lista com 399 municípios")
    ids = [str(item.get("id", "")) for item in payload if isinstance(item, dict)]
    if (
        len(ids) != 399
        or len(set(ids)) != 399
        or any(len(key) != 7 or not key.startswith("41") for key in ids)
    ):
        raise ValueError("códigos municipais do Paraná são incoerentes")
    if not any(
        item.get("id") == 4106902 and item.get("nome") == "Curitiba" for item in payload
    ):
        raise ValueError("Curitiba não foi encontrada na resposta")
    return payload


def execute(raw_path: Path, report_path: Path, manifest_path: Path) -> dict:
    if raw_path.exists():
        raise FileExistsError(
            f"raw imutável já existe: {raw_path}; use outro caminho de snapshot"
        )
    request = Request(
        URL, headers={"User-Agent": "SIT-mvp-demo-2026/1.0", "Accept-Encoding": "gzip"}
    )
    with urlopen(request, timeout=60) as response:
        wire_body = response.read()
        headers = dict(response.headers)
        status = response.status
        final_url = response.url
    entity_body = (
        gzip.decompress(wire_body)
        if headers.get("content-encoding") == "gzip"
        else wire_body
    )
    validate_pr_payload(entity_body)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(entity_body)
    timestamp = datetime.now(UTC).isoformat()
    entry = {
        "fonte": "IBGE API de Localidades",
        "url": URL,
        "metodo": "GET",
        "parametros": {},
        "periodo": "vigente na execução",
        "data_hora_utc": timestamp,
        "status_http": status,
        "url_final": final_url,
        "redirects": [],
        "content_type": headers.get("content-type"),
        "content_encoding": headers.get("content-encoding"),
        "tamanho_transferido": len(wire_body),
        "tamanho": len(entity_body),
        "sha256": hashlib.sha256(entity_body).hexdigest(),
        "arquivo": str(raw_path),
        "licenca": None,
        "versao_snapshot": timestamp,
        "validacao": "schema_e_contagem_validados",
    }
    report = {
        "executado_em": timestamp,
        "controle": "API de Localidades do IBGE — municípios do Paraná",
        "http": entry,
        "proxy_presente": any(
            os.environ.get(key) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
        ),
        "diagnostico_tamanho": "7917 representa gzip transferido; 170538 representa o JSON descomprimido. O manifesto antigo mediu bytes de transferência e requests mediu conteúdo automaticamente descomprimido.",
    }
    for path, payload in ((report_path, report), (manifest_path, [entry])):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path(
            "data/raw/ibge_localidades/2026-08-12/preflight_municipios_PR.json"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/quality/mvp-demo-2026/network-preflight.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/quality/mvp-demo-2026/manifesto-coleta.json"),
    )
    args = parser.parse_args(argv)
    print(
        json.dumps(
            execute(args.raw, args.report, args.manifest), ensure_ascii=False, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
