"""Registry extensível: cada fonte registra uma factory, sem if/elif central."""

from __future__ import annotations

from collections.abc import Callable

from .contracts import Collector

CollectorFactory = Callable[[], Collector]
COLLECTORS: dict[str, CollectorFactory] = {}


def register_collector(name: str, factory: CollectorFactory) -> None:
    normalized = name.strip().lower()
    if not normalized or normalized in COLLECTORS:
        raise ValueError(f"nome de coletor inválido ou duplicado: {name!r}")
    COLLECTORS[normalized] = factory


def build_collectors(names: list[str]) -> list[Collector]:
    # Descoberta localizada mantém o registry extensível e funciona em processo limpo.
    for name in names:
        if name not in COLLECTORS:
            try:
                __import__(f"ice_sul.extract.{name}")
            except ModuleNotFoundError as exc:
                if exc.name != f"ice_sul.extract.{name}":
                    raise
    missing = [name for name in names if name not in COLLECTORS]
    if missing:
        raise KeyError(f"coletores não registrados: {', '.join(missing)}")
    return [COLLECTORS[name]() for name in names]
