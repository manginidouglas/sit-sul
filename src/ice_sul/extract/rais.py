"""Aquisição auditável dos microdados de vínculos da RAIS.

O PDET publica a RAIS em arquivos compactados grandes. Este módulo mantém o
download separado da transformação e registra os metadados necessários para
repetir uma coleta, sem tratar CAGED como substituto.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from ice_sul.extract.http import download


OFFICIAL_ROOT = "https://ftp.mtps.gov.br/pdet/microdados/RAIS"
SOURCE_VERSION = "RAIS 2024, vínculos (estoque em 31/12)"
UF_CODES = (
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO"
).split()


@dataclass(frozen=True)
class RaisArchive:
    """Descrição de um arquivo oficial, mantida explícita no manifesto."""

    uf: str
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def official_archives(year: int = 2024) -> list[RaisArchive]:
    """Retorna a distribuição oficial por UF usada pela edição.

    O nome segue a convenção do PDET. URLs podem ser substituídas por um
    manifesto oficial espelho com os mesmos arquivos e hashes.
    """

    return [
        RaisArchive(uf, f"{OFFICIAL_ROOT}/{year}/RAIS_VINC_PUB_{uf}.7z")
        for uf in UF_CODES
    ]


def collect(
    destination: Path,
    *,
    year: int = 2024,
    archives: list[RaisArchive] | None = None,
) -> Path:
    """Baixa arquivos imutáveis e grava um manifesto auditável."""

    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for archive in archives or official_archives(year):
        entries.append(
            download(
                archive.url,
                destination / archive.filename,
                source="MTE/PDET — microdados RAIS vínculos",
                indicators=["MER-02", "MER-DIAG-01"],
                period=str(year),
                timeout=180,
            )
        )
    manifest = destination / "manifest.json"
    if manifest.exists():
        raise FileExistsError(f"raw imutável já existe: {manifest}")
    manifest.write_text(
        json.dumps(
            {
                "fonte": "MTE/PDET",
                "versao": SOURCE_VERSION,
                "ano": year,
                "conceito": "um vínculo ativo em 31/12; não é trabalhador único, estabelecimento ou vínculo movimentado",
                "arquivos": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--destination", type=Path, default=Path("data/raw/rais/2024"))
    args = parser.parse_args()
    print(collect(args.destination, year=args.year))


if __name__ == "__main__":
    main()
