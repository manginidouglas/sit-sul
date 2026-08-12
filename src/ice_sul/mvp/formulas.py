"""Fórmulas puras dos indicadores; nenhuma função faz chamadas externas."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping


def competitividade_hhi(acessos: Iterable[float]) -> float | None:
    valores = [float(x) for x in acessos if x is not None]
    total = sum(valores)
    if total <= 0 or any(x < 0 for x in valores):
        return None
    return 1.0 - sum((x / total) ** 2 for x in valores)


def media_ponderada_conjuntos(valores: Mapping[str, float], pesos: Mapping[str, float]) -> float | None:
    comuns = [chave for chave in valores if chave in pesos and pesos[chave] > 0]
    total = sum(pesos[chave] for chave in comuns)
    if not comuns or total <= 0:
        return None
    return sum(valores[chave] * pesos[chave] for chave in comuns) / total


def conectividade_aerea(aeroportos: Iterable[tuple[float, int, int]], limite_minutos: float = 120) -> float:
    """Recebe (tempo, decolagens, destinos), incluindo somente tempos elegíveis."""
    return sum(math.sqrt(frequencia * destinos) * math.exp(-tempo / 60)
               for tempo, frequencia, destinos in aeroportos
               if 0 <= tempo <= limite_minutos and frequencia >= 0 and destinos >= 0)


def decaimento_acessibilidade(tempo_minutos: float, truncamento: float = 360) -> float:
    if tempo_minutos < 0:
        raise ValueError("tempo não pode ser negativo")
    return 0.0 if tempo_minutos > truncamento else 2 ** (-tempo_minutos / 60)


def mercado_acessivel(recursos_tempos: Iterable[tuple[float, float]], truncamento: float = 360) -> float:
    return sum(recurso * decaimento_acessibilidade(tempo, truncamento)
               for recurso, tempo in recursos_tempos if recurso >= 0)


def diversificacao(empregos_setoriais: Iterable[float]) -> float | None:
    valores = [float(x) for x in empregos_setoriais if x is not None]
    total = sum(valores)
    if total <= 0 or any(x < 0 for x in valores):
        return None
    return 1 - sum((x / total) ** 2 for x in valores)


def densidade_estabelecimentos(ativos: int, populacao_18_64: int) -> float | None:
    return None if populacao_18_64 <= 0 else 1000 * ativos / populacao_18_64


def crescimento_real_acumulado(pib_final: float, pib_inicial: float, deflator_final: float, deflator_inicial: float) -> float | None:
    if min(pib_inicial, deflator_final, deflator_inicial) <= 0:
        return None
    return (pib_final / pib_inicial) / (deflator_final / deflator_inicial) - 1
