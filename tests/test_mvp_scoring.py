import math
import pytest
from ice_sul.mvp.scoring import DegenerateIndicator, axis_score, minmax, overall, winsorize
from ice_sul.mvp.validate import validate_municipal_keys, validate_scores


def test_winsorization_preserves_na_and_flags_extremes():
    values, lo, hi, flags = winsorize([None, 0, 1, 2, 100], .25, .75)
    assert values == [None, .75, 1, 2, 26.5]
    assert flags == [False, True, False, False, True]


def test_log1p_order_is_available_to_pipeline():
    assert math.log1p(0) == 0 and math.log1p(9) == pytest.approx(math.log(10))


def test_minmax_directions_domain_and_degenerate():
    assert minmax([0, 5, 10, None], "positiva")[0] == [0, 50, 100, None]
    assert minmax([0, 5, 10], "negativa")[0] == [100, 50, 0]
    with pytest.raises(DegenerateIndicator): minmax([1, 1], "positiva")
    validate_scores([0, 50, 100, None])
    with pytest.raises(ValueError): validate_scores([101])


def test_coverage_boundary_weight_renormalization_and_overall():
    weights = {"a": .2, "b": .3, "c": .5}
    assert axis_score({"a": 100, "b": None, "c": 50}, weights)[0] is None
    score, coverage = axis_score({"a": 100, "b": 0, "c": 50}, weights)
    assert (score, coverage) == (45, 1)
    score, coverage = axis_score({"a": None, "b": 100, "c": 40}, weights)
    assert coverage == .8 and score == 62.5
    assert overall(score, 50) == 56.25 and overall(None, 50) is None


def test_keys_duplicates_and_count():
    valid = [{"municipio_id": "1234567"}, {"municipio_id": "7654321"}]
    validate_municipal_keys(valid, expected=2)
    with pytest.raises(ValueError): validate_municipal_keys(valid + [valid[0]], expected=3)
