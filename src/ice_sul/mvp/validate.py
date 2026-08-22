"""Contratos de validação das entradas do MVP."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

ALLOWED_UFS = {"PR", "SC", "RS"}


def validate_municipal_keys(
    rows: Iterable[Mapping[str, object]],
    canonical: Iterable[Mapping[str, object]],
    *,
    expected_count: int = 1191,
) -> None:
    """Exige igualdade exata com um cadastro canônico íntegro e coerente."""
    rows = list(rows)
    canonical = list(canonical)
    if len(canonical) != expected_count:
        raise ValueError(
            f"cadastro canônico inválido: esperado {expected_count}, "
            f"encontrado {len(canonical)}"
        )
    canonical_ids = [str(row.get("municipio_id", "")) for row in canonical]
    _validate_ids(canonical_ids, "cadastro canônico")
    expected = {str(row["municipio_id"]): row for row in canonical}
    for row in canonical:
        if row.get("uf_sigla") not in ALLOWED_UFS:
            raise ValueError("cadastro canônico contém UF fora de PR, SC e RS")
        if not str(row.get("municipio_nome", "")).strip():
            raise ValueError("cadastro canônico contém nome municipal vazio")

    ids = [str(row.get("municipio_id", "")) for row in rows]
    _validate_ids(ids, "universo informado")
    missing = sorted(set(expected) - set(ids))
    additional = sorted(set(ids) - set(expected))
    if missing or additional or len(ids) != len(expected):
        raise ValueError(
            "universo não coincide exatamente com o cadastro canônico; "
            f"ausentes={missing[:5]}, adicionais={additional[:5]}"
        )
    for row in rows:
        reference = expected[str(row["municipio_id"])]
        for field in ("municipio_nome", "uf_sigla"):
            if str(row.get(field, "")) != str(reference.get(field, "")):
                raise ValueError(
                    f"{field} incoerente com cadastro canônico: {row['municipio_id']}"
                )


def _validate_ids(ids: list[str], label: str) -> None:
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"{label} contém municipio_id duplicado: {duplicates[:5]}")
    invalid = [key for key in ids if len(key) != 7 or not key.isdigit()]
    if invalid:
        raise ValueError(f"{label} contém municipio_id que não possui sete dígitos")


def validate_scores(values: Iterable[float | None]) -> None:
    if any(value is not None and not 0 <= value <= 100 for value in values):
        raise ValueError("score fora do domínio 0–100")
