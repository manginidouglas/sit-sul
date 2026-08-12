from __future__ import annotations
from collections import Counter
from collections.abc import Iterable, Mapping


def validate_municipal_keys(rows: Iterable[Mapping[str, object]], canonical: Iterable[Mapping[str, object]]) -> None:
    rows, canonical = list(rows), list(canonical)
    ids = [str(row.get("municipio_id", "")) for row in rows]
    expected = {str(row["municipio_id"]): row for row in canonical}
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    if duplicates or any(len(key) != 7 or not key.isdigit() for key in ids):
        raise ValueError("municipio_id inválido ou duplicado")
    if set(ids) != set(expected) or len(ids) != len(expected):
        raise ValueError("universo não coincide exatamente com o cadastro canônico")
    for row in rows:
        ref = expected[str(row["municipio_id"])]
        for field in ("municipio_nome", "uf_sigla"):
            if row.get(field) not in (None, "") and str(row[field]) != str(ref.get(field, "")):
                raise ValueError(f"{field} incoerente com cadastro canônico: {row['municipio_id']}")


def validate_scores(values: Iterable[float | None]) -> None:
    if any(value is not None and not 0 <= value <= 100 for value in values):
        raise ValueError("score fora do domínio 0–100")
