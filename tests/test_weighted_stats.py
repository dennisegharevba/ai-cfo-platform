from agents.weighted_stats import weighted_mean, weighted_stdev


def test_weighted_mean_basic():
    assert weighted_mean([10.0, 20.0], [1.0, 1.0]) == 15.0


def test_weighted_mean_respects_weights():
    # Heavily weighted toward the second value -> mean should sit closer to it
    result = weighted_mean([0.0, 100.0], [1.0, 9.0])
    assert result == 90.0


def test_weighted_mean_zero_total_weight_returns_zero():
    assert weighted_mean([10.0, 20.0], [0.0, 0.0]) == 0.0


def test_weighted_stdev_zero_for_identical_values():
    assert weighted_stdev([50.0, 50.0, 50.0], [1.0, 1.0, 1.0]) == 0.0


def test_weighted_stdev_positive_for_spread_values():
    result = weighted_stdev([0.0, 100.0], [1.0, 1.0])
    assert result > 0


def test_weighted_stdev_single_value_returns_zero():
    assert weighted_stdev([50.0], [1.0]) == 0.0


def test_weighted_stdev_zero_total_weight_returns_zero():
    assert weighted_stdev([10.0, 20.0], [0.0, 0.0]) == 0.0
