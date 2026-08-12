"""Contrato estável compartilhado por todos os coletores."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class CollectionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    BLOCKED_SOURCE = "blocked_source"
    BLOCKED_ENVIRONMENT = "blocked_environment"
    ENDPOINT_REVIEW = "endpoint_review"
    UNAVAILABLE = "unavailable"
    FAILED_VALIDATION = "failed_validation"


@dataclass
class CollectionResult:
    source: str
    status: CollectionStatus
    artifacts: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    manifest_entries: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Collector(Protocol):
    """Interface mínima: nome estável e método collect sem efeitos cruzados."""

    source: str

    def collect(self) -> CollectionResult: ...


@dataclass
class CollectionRun:
    status: CollectionStatus
    results: list[CollectionResult]
    manifest_path: Path | None = None
