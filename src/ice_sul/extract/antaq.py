"""Coleta auditável dos dados abertos do Estatístico Aquaviário da ANTAQ."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError

from .contracts import CollectionResult, CollectionStatus
from .http import download
from .registry import register_collector

SOURCE = "ANTAQ — Estatístico Aquaviário"
INDICATORS = ["INF-LOG-04"]
DEFAULT_URL = "https://web3.antaq.gov.br/ea/sense/download.html#pt"

@dataclass
class AntaqCollector:
    """Baixa um recurso oficial já identificado; não raspa o painel Qlik."""

    resource_url: str = DEFAULT_URL
    raw_path: Path = Path("data/raw/antaq/estatistico-aquaviario.bin")
    period: str = "12 meses completos mais recentes disponíveis até 2026-08-12"
    source: str = "antaq"

    def collect(self) -> CollectionResult:
        try:
            entry = download(
                self.resource_url, self.raw_path, source=SOURCE,
                indicators=INDICATORS, period=self.period,
            )
        except HTTPError as exc:
            status = (CollectionStatus.BLOCKED_SOURCE if exc.code in {401, 403}
                      else CollectionStatus.ENDPOINT_REVIEW)
            return CollectionResult(
                source=self.source, status=status, indicators=INDICATORS,
                errors=[f"HTTP {exc.code}: {self.resource_url}"],
                warnings=["O erro do portal não demonstra indisponibilidade dos dados abertos."],
            )
        except (URLError, TimeoutError) as exc:
            return CollectionResult(
                source=self.source, status=CollectionStatus.BLOCKED_ENVIRONMENT,
                indicators=INDICATORS, errors=[str(exc)],
            )
        except (ValueError, FileExistsError) as exc:
            return CollectionResult(
                source=self.source, status=CollectionStatus.FAILED_VALIDATION,
                indicators=INDICATORS, errors=[str(exc)],
            )
        return CollectionResult(
            source=self.source, status=CollectionStatus.SUCCESS,
            artifacts=[str(self.raw_path)], indicators=INDICATORS,
            manifest_entries=[entry],
        )

    @staticmethod
    def write_result(result: CollectionResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _factory() -> AntaqCollector:
    return AntaqCollector()

register_collector("antaq", _factory)
