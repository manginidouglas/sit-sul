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
GENERIC_GROUPS = {"", "outros", "outras", "nao informado", "n/a", "na"}


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
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        text = str(value).strip()
        return Decimal(text.replace(".", "").replace(",", ".") if "," in text else text)
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


def fixed_snapshot(
    rows: Iterable[Mapping[str, object]], municipality_ids: Iterable[str], period: str
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Agrega a tabela anual em colunas e devolve produto e QA por unidade.

    A primeira saída contém os três indicadores (INF-DIG-01 ainda como contagem
    intermediária). A segunda preserva as versões de competitividade por CNPJ e
    por unidade híbrida: grupo informativo; caso contrário, CNPJ.
    """
    universe = set(municipality_ids)
    total: defaultdict[str, Decimal] = defaultdict(Decimal)
    fast: defaultdict[str, Decimal] = defaultdict(Decimal)
    fiber: defaultdict[str, Decimal] = defaultdict(Decimal)
    cnpjs: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    hybrid: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    groups: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        municipality = str(row["Código IBGE Município"]).strip()
        if municipality not in universe or _key(row["Tipo de Produto"]) != "internet":
            continue
        raw_accesses = row[period]
        accesses = Decimal(0) if str(raw_accesses).strip() == "" else _decimal(raw_accesses)
        if accesses < 0:
            raise ValueError("acessos negativos")
        cnpj = str(row["CNPJ"]).strip()
        group = str(row["Grupo Econômico"]).strip()
        unit = f"grupo:{_key(group)}" if _key(group) not in GENERIC_GROUPS else f"cnpj:{cnpj}"
        total[municipality] += accesses
        cnpjs[municipality][cnpj] += accesses
        hybrid[municipality][unit] += accesses
        if unit.startswith("grupo:"):
            groups[group].add(cnpj)
        if _decimal(row["Velocidade"]) >= 100:
            fast[municipality] += accesses
        if _key(row["Meio de Acesso"]) == "fibra":
            fiber[municipality] += accesses

    indicators, comparison = [], []
    for municipality in municipality_ids:
        accesses = total[municipality]
        indicators.append(_output(municipality, "INF-DIG-01-NUM", fast[municipality] if accesses else None, period, accesses > 0, zero=accesses > 0 and fast[municipality] == 0))
        indicators[-1].update({"acessos_ge_100_mbps": str(fast[municipality]), "total_acessos_internet": str(accesses)})
        share = None if accesses == 0 else 100 * fiber[municipality] / accesses
        indicators.append(_output(municipality, "INF-DIG-02", share, period, accesses > 0, zero=accesses > 0 and fiber[municipality] == 0))
        indicators[-1].update({"acessos_fibra": str(fiber[municipality]), "total_acessos_internet": str(accesses)})
        cnpj_value = _competition(cnpjs[municipality], accesses)
        hybrid_value = _competition(hybrid[municipality], accesses)
        # A unidade oficial é híbrida: grupo Anatel informativo; caso o grupo
        # seja genérico, o CNPJ permanece individual. A versão CNPJ é QA.
        indicators.append(_output(municipality, "INF-DIG-03", hybrid_value, period, accesses > 0, zero=hybrid_value == 0))
        indicators[-1].update({"total_acessos_internet": str(accesses), "unidades_economicas_hibridas": len(hybrid[municipality])})
        comparison.append({"municipio_id": municipality, "periodo_referencia": period, "competitividade_cnpj": _format(cnpj_value), "competitividade_hibrida": _format(hybrid_value), "diferenca_absoluta": _format(None if cnpj_value is None else abs(cnpj_value - hybrid_value)), "cnpjs": len(cnpjs[municipality]), "unidades_hibridas": len(hybrid[municipality])})
    comparison.append({"municipio_id": "__METADATA__", "periodo_referencia": period, "competitividade_cnpj": "", "competitividade_hibrida": "", "diferenca_absoluta": "", "cnpjs": sum(len(v) for v in groups.values()), "unidades_hibridas": len(groups)})
    return indicators, comparison


def _competition(units: Mapping[str, Decimal], total: Decimal) -> Decimal | None:
    if total == 0:
        return None
    return Decimal(1) - sum((value / total) ** 2 for value in units.values())


def mobile_population_indicator(
    rows: Iterable[Mapping[str, object]], municipality_ids: Iterable[str],
    cutoff: str = "2026-08"
) -> list[dict[str, object]]:
    """Seleciona um único e mais recente mês municipal 4G5G até o corte."""
    candidates: defaultdict[str, defaultdict[str, set[Decimal]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        municipality = str(_value(row, "Código Município")).strip()
        technology = _key(_value(row, "Tecnologia"))
        operator = _key(_value(row, "Operadora"))
        if technology != "4g5g" or operator != "todas":
            continue
        period_raw = str(_value(row, "Período")).strip()
        month, year = period_raw.split("-")
        period = f"{year}-{int(month):02d}"
        raw_value = _value(row, "% moradores cobertos")
        if str(raw_value).strip() == "":
            continue
        value = _decimal(raw_value)
        # O CSV municipal corrente rotula o campo como percentual, mas o
        # publica em proporção (0..1).
        if value <= 1:
            value *= 100
        if not Decimal(0) <= value <= Decimal(100):
            raise ValueError("cobertura populacional fora de 0..100")
        if period > cutoff:
            continue
        candidates[period][municipality].add(value)
    if not candidates:
        raise ValueError("nenhum período municipal 4G5G disponível até o corte")
    selected = max(candidates)
    divergent = [mid for mid, found in candidates[selected].items() if len(found) > 1]
    if divergent:
        raise ValueError("cobertura municipal duplicada e divergente")
    values = {mid: next(iter(found)) for mid, found in candidates[selected].items()}
    return [
        _output(mid, "INF-DIG-04", values[mid], selected, True, zero=values[mid] == 0)
        if mid in values
        else _output(mid, "INF-DIG-04", None, selected, False)
        for mid in municipality_ids
    ]


def _output(municipality: str, indicator: str, value: Decimal | None, period: str, observed: bool, *, zero: bool = False) -> dict[str, object]:
    flag = "ausente" if not observed or value is None else ("zero_observado" if zero else "observado")
    return {
        "municipio_id": municipality,
        "indicador_id": indicator,
        "valor_bruto": _format(value),
        "periodo_referencia": period,
        "flag_qualidade": flag,
    }


def _format(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f").rstrip("0").rstrip(".")
