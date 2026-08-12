"""Execução sequencial, independente e tolerante a falhas de fontes."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError

from .contracts import CollectionResult, CollectionRun, CollectionStatus, Collector


class CollectorValidationError(ValueError):
    """Falha de contrato ou validação substantiva do coletor."""


def _failure(source: str, exc: Exception) -> CollectionResult:
    status = CollectionStatus.UNAVAILABLE
    evidence = {"exception": type(exc).__name__, "message": str(exc)}
    if isinstance(exc, CollectorValidationError):
        status = CollectionStatus.FAILED_VALIDATION
    elif isinstance(exc, HTTPError):
        evidence["http_status"] = exc.code
        if exc.code in {401, 403}:
            status = CollectionStatus.BLOCKED_SOURCE
        elif exc.code in {429, 502, 503, 504}:
            status = CollectionStatus.UNAVAILABLE
        else:
            status = CollectionStatus.ENDPOINT_REVIEW
    elif isinstance(exc, (ModuleNotFoundError, PermissionError)):
        status = CollectionStatus.BLOCKED_ENVIRONMENT
    return CollectionResult(
        source=source,
        status=status,
        manifest_entries=[{"fonte": source, "evidencia_falha": evidence}],
        errors=[str(exc)],
    )


def run_collectors(
    collectors: list[Collector], manifest_path: Path | None = None
) -> CollectionRun:
    """Executa todos os coletores mesmo quando uma fonte falha."""
    results: list[CollectionResult] = []
    for collector in collectors:
        try:
            result = collector.collect()
            if result.source != collector.source:
                raise CollectorValidationError("source retornada difere do registro")
        except Exception as exc:  # fronteira deliberada de isolamento entre fontes
            result = _failure(collector.source, exc)
        results.append(result)

    if all(result.status == CollectionStatus.SUCCESS for result in results):
        overall = CollectionStatus.SUCCESS
    elif any(result.status == CollectionStatus.SUCCESS for result in results):
        overall = CollectionStatus.PARTIAL
    else:
        overall = CollectionStatus.UNAVAILABLE
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {"status": overall, "coletores": [item.as_dict() for item in results]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return CollectionRun(overall, results, manifest_path)
