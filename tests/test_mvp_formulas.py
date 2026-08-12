import math
import pytest
from ice_sul.mvp.formulas import (competitividade_hhi, conectividade_aerea, decaimento_acessibilidade,
    densidade_estabelecimentos, diversificacao, media_ponderada_conjuntos, mercado_acessivel)


def test_hhi_and_missing_market():
    assert competitividade_hhi([50, 50]) == pytest.approx(.5)
    assert competitividade_hhi([100]) == 0
    assert competitividade_hhi([]) is None


def test_dec_fec_weighted():
    assert media_ponderada_conjuntos({"a": 10, "b": 20}, {"a": .25, "b": .75}) == 17.5


def test_air_connectivity_multiple_airports_and_limit():
    result = conectividade_aerea([(0, 100, 4), (60, 25, 4), (121, 999, 9)])
    assert result == pytest.approx(20 + 10 / math.e)


def test_accessibility_half_life_and_truncation():
    assert decaimento_acessibilidade(0) == 1
    assert decaimento_acessibilidade(60) == .5
    assert decaimento_acessibilidade(360) == pytest.approx(.015625)
    assert decaimento_acessibilidade(361) == 0
    assert mercado_acessivel([(100, 0), (100, 60), (999, 361)]) == 150


def test_diagnostics():
    assert diversificacao([50, 50]) == .5
    assert densidade_estabelecimentos(10, 100) == 100
