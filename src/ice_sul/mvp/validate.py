from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping


def validate_municipal_keys(rows: Iterable[Mapping[str, object]], expected: int = 1191) -> None:
    ids = [str(row.get("municipio_id", "")) for row in rows]
    if len(ids) != expected:
        raise ValueError(f"universo deve conter {expected} municípios; recebeu {len(ids)}")
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    if duplicates or any(len(key) != 7 or not key.isdigit() for key in ids):
        raise ValueError("municipio_id inválido ou duplicado")


def validate_scores(values: Iterable[float | None]) -> None:
    if any(value is not None and not 0 <= value <= 100 for value in values):
        raise ValueError("score fora do domínio 0–100")
