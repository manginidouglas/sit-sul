"""Transformações auditáveis dos arquivos abertos da Anatel.

As funções operam sobre iteráveis de dicionários para permitir tanto testes
pequenos quanto leitura em streaming dos CSVs nacionais.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
import unicodedata

OUTPUT_COLUMNS = (
    "municipio_id",
    "indicador_id",
    "valor_bruto",
    "periodo_referencia",
    "flag_qualidade",
)


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).strip().lower()


def _value(row: Mapping[str, object], *names: str) -> object:
    normalized = {_key(k): v for k, v in row.items()}
    for name in names:
        if _key(name) in normalized:
            return normalized[_key(name)]
    raise ValueError(f"schema Anatel inválido: ausente {names[0]!r}")


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value).strip().replace(".", "").replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"número Anatel inválido: {value!r}") from exc


def _period(row: Mapping[str, object]) -> str:
    year = str(_value(row, "Ano")).strip()
    month = int(str(_value(row, "Mês", "Mes")).strip())
    if len(year) != 4 or not 1 <= month <= 12:
        raise ValueError("período Anatel inválido")
    return f"{year}-{month:02d}"


def parse_fixed_access(row: Mapping[str, object]) -> dict[str, object]:
    """Normaliza uma linha do SCM e conserva as categorias declaradas."""
    municipio = str(_value(row, "Código IBGE Município", "codigo_ibge")).strip()
    if len(municipio) != 7 or not municipio.isdigit():
        raise ValueError(f"código IBGE inválido: {municipio!r}")
    return {
        "municipio_id": municipio,
        "periodo": _period(row),
        "cnpj": str(_value(row, "CNPJ", "cnpj")).strip(),
        "velocidade_mbps": _decimal(_value(row, "Velocidade", "velocidade_contratada_mbps")),
        "meio": str(_value(row, "Meio de Acesso", "Tecnologia", "tipo")).strip(),
        "produto": str(_value(row, "Tipo de Produto", "tipo")).strip(),
        "acessos": _decimal(_value(row, "Acessos", "acessos")),
    }


def fixed_indicators(
    rows: Iterable[Mapping[str, object]],
    municipality_ids: Iterable[str],
    period: str,
    populations: Mapping[str, int | float | Decimal] | None = None,
) -> list[dict[str, object]]:
    """Calcula INF-DIG-01/02/03 no universo, sem imputar ausências.

    A unidade empresarial de INF-DIG-03 é o CNPJ informado pela Anatel, não o
    campo ``Grupo Econômico``. Apenas ``Tipo de Produto = INTERNET`` integra o
    mercado comparável. Fibra é identificada pelo ``Meio de Acesso = Fibra``.
    """
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    fast: defaultdict[str, Decimal] = defaultdict(Decimal)
    fiber: defaultdict[str, Decimal] = defaultdict(Decimal)
    providers: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    universe = set(municipality_ids)
    for raw in rows:
        item = parse_fixed_access(raw)
        if item["periodo"] != period or _key(item["produto"]) != "internet":
            continue
        if str(item["municipio_id"]) not in universe:
            continue
        municipality = str(item["municipio_id"])
        accesses = item["acessos"]
        if accesses < 0:
            raise ValueError("acessos negativos")
        totals[municipality] += accesses
        if item["velocidade_mbps"] >= 100:
            fast[municipality] += accesses
        if _key(item["meio"]) == "fibra":
            fiber[municipality] += accesses
        providers[municipality][str(item["cnpj"])] += accesses

    output: list[dict[str, object]] = []
    for municipality in universe:
        total = totals[municipality]
        population = (populations or {}).get(municipality)
        density = None if population is None or Decimal(str(population)) <= 0 else 100 * fast[municipality] / Decimal(str(population))
        output.append(_output(municipality, "INF-DIG-01", density, period, population is not None))
        share = None if total == 0 else 100 * fiber[municipality] / total
        output.append(_output(municipality, "INF-DIG-02", share, period, total > 0, zero=(fiber[municipality] == 0 and total > 0)))
        competition = None
        if total > 0:
            hhi = sum((value / total) ** 2 for value in providers[municipality].values())
            competition = Decimal(1) - hhi
        output.append(_output(municipality, "INF-DIG-03", competition, period, total > 0, zero=(competition == 0)))
    return output


def mobile_population_indicator(
    rows: Iterable[Mapping[str, object]], municipality_ids: Iterable[str]
) -> list[dict[str, object]]:
    """Extrai a medida municipal oficial para operadora Todas e tecnologia 4G5G."""
    values: dict[str, tuple[Decimal, str]] = {}
    for row in rows:
        municipality = str(_value(row, "Código Município")).strip()
        technology = _key(_value(row, "Tecnologia"))
        operator = _key(_value(row, "Operadora"))
        if technology != "4g5g" or operator != "todas":
            continue
        period_raw = str(_value(row, "Período")).strip()
        month, year = period_raw.split("-")
        period = f"{year}-{int(month):02d}"
        value = _decimal(_value(row, "% moradores cobertos"))
        # O CSV municipal corrente rotula o campo como percentual, mas o
        # publica em proporção (0..1).
        if value <= 1:
            value *= 100
        if not Decimal(0) <= value <= Decimal(100):
            raise ValueError("cobertura populacional fora de 0..100")
        if municipality in values:
            if values[municipality] != (value, period):
                raise ValueError("cobertura municipal duplicada e divergente")
            continue
        values[municipality] = (value, period)
    return [
        _output(mid, "INF-DIG-04", values[mid][0], values[mid][1], True, zero=values[mid][0] == 0)
        if mid in values
        else _output(mid, "INF-DIG-04", None, "", False)
        for mid in municipality_ids
    ]


def _output(municipality: str, indicator: str, value: Decimal | None, period: str, observed: bool, *, zero: bool = False) -> dict[str, object]:
    flag = "ausente" if not observed or value is None else ("zero_observado" if zero else "observado")
    return {
        "municipio_id": municipality,
        "indicador_id": indicator,
        "valor_bruto": "" if value is None else format(value, ".12f").rstrip("0").rstrip("."),
        "periodo_referencia": period,
        "flag_qualidade": flag,
    }
