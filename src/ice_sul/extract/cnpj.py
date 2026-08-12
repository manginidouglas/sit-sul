"""Descoberta e download reproduzível dos arquivos abertos do CNPJ/RFB."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

OFFICIAL_INDEX = "https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/"
REQUIRED_KINDS = ("Estabelecimentos", "Simples", "Municipios")
FILE_RE = re.compile(r"(?:Estabelecimentos\d*|Simples|Municipios)\.zip$", re.I)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def list_official_files(snapshot: str, *, base_url: str = OFFICIAL_INDEX,
                        timeout: int = 60) -> list[str]:
    """Lê o índice oficial do snapshot YYYY-MM, sem adivinhar nomes de partes."""
    if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", snapshot):
        raise ValueError("snapshot deve usar YYYY-MM")
    index_url = urljoin(base_url.rstrip("/") + "/", snapshot + "/")
    request = Request(index_url, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = _Links()
    parser.feed(html)
    files = sorted({urljoin(index_url, href) for href in parser.hrefs
                    if FILE_RE.search(href.split("?")[0])})
    found = {kind: any(kind.lower() in url.lower() for url in files)
             for kind in REQUIRED_KINDS}
    missing = [kind for kind, present in found.items() if not present]
    if missing:
        raise ValueError(f"índice oficial incompleto; faltam: {', '.join(missing)}")
    return files


def download_files(urls: list[str], destination: Path, *, snapshot: str,
                   timeout: int = 180) -> Path:
    """Baixa em streaming, preserva ZIP bruto e grava hash/volume no manifesto."""
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for url in urls:
        target = destination / url.rsplit("/", 1)[-1]
        if target.exists():
            raise FileExistsError(f"raw imutável já existe: {target}")
        digest = hashlib.sha256()
        size = 0
        request = Request(url, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"})
        with urlopen(request, timeout=timeout) as response, target.open("xb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
                size += len(block)
            final_url, status = response.url, response.status
        entries.append({"url": url, "url_final": final_url, "status_http": status,
                        "arquivo": str(target), "bytes": size,
                        "sha256": digest.hexdigest()})
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps({"fonte": "Receita Federal — Dados Abertos do CNPJ",
        "indice_oficial": OFFICIAL_INDEX, "snapshot": snapshot,
        "extraido_em": datetime.now(UTC).isoformat(), "arquivos": entries},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baixa o snapshot oficial do CNPJ")
    parser.add_argument("--snapshot", required=True, help="YYYY-MM")
    parser.add_argument("--output", type=Path, default=Path("data/raw/cnpj"))
    args = parser.parse_args(argv)
    urls = list_official_files(args.snapshot)
    print(download_files(urls, args.output / args.snapshot, snapshot=args.snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
