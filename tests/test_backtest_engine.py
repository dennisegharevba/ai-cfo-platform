from datetime import date, timedelta

from agents.backtest_engine import (
    run_backtest, spearman_correlation, approximate_significance_threshold, _rank_transform,
)


def test_rank_transform_no_ties():
    assert _rank_transform([30.0, 10.0, 20.0]) == [3.0, 1.0, 2.0]


def test_rank_transform_with_ties_uses_average_rank():
    # Two tied values at the bottom should each get rank 1.5 (average of 1,2)
    result = _rank_transform([10.0, 10.0, 30.0])
    assert result[0] == 1.5
    assert result[1] == 1.5
    assert result[2] == 3.0


def test_spearman_perfect_positive_monotonic():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [10.0, 20.0, 35.0, 40.0, 1000.0]  # non-linear but perfectly monotonic
    result = spearman_correlation(a, b)
    assert abs(result - 1.0) < 1e-9  # floating-point, not exact equality


def test_spearman_perfect_negative_monotonic():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [50.0, 40.0, 30.0, 20.0, 10.0]
    result = spearman_correlation(a, b)
    assert abs(result - (-1.0)) < 1e-9


def test_spearman_too_few_points_returns_none():
    assert spearman_correlation([1.0], [1.0]) is None


def test_significance_threshold_shrinks_with_larger_sample():
    small = approximate_significance_threshold(10)
    large = approximate_significance_threshold(1000)
    assert small > large


def test_significance_threshold_none_for_tiny_sample():
    assert approximate_significance_threshold(2) is None


def _price_series(start_date, n_days, values):
    return [(start_date + timedelta(days=i), v) for i, v in enumerate(values)]


def test_run_backtest_computes_correlation_from_real_synthetic_relationship():
    """
    A genuinely constructed signal: higher score always precedes a
    LARGER PERCENTAGE forward return. Price anchor points are set
    EXPLICITLY per signal date (rather than derived from one global
    price formula) so the intended relationship is unambiguous and
    doesn't depend on reasoning through compounding/percentage-base
    effects that a smooth formula could accidentally invert.
    """
    base = date(2020, 1, 1)
    signal_scores = []
    prices = []
    for i in range(20):
        as_of = base + timedelta(days=i * 30)      # 30-day spacing -> no overlap with the 20-day window
        forward = as_of + timedelta(days=20)
        start_price = 100.0
        # Forward return scales directly with i: 1%, 2%, 3%, ... 20%
        end_price = start_price * (1.0 + (i + 1) / 100.0)
        prices.append((as_of, start_price))
        prices.append((forward, end_price))
        signal_scores.append((as_of, float(i)))
    prices.sort(key=lambda t: t[0])

    result = run_backtest("Test", "ASSET", signal_scores, prices, forward_window_days=20)
    assert result.sample_size == 20
    assert result.correlation > 0.9  # deliberately near-perfect monotonic relationship
    assert result.skipped_dates == 0


def test_run_backtest_skips_dates_with_no_matching_price_data():
    base = date(2020, 1, 1)
    signal_scores = [(base, 50.0), (date(2025, 1, 1), 50.0)]  # second date way outside price history
    prices = _price_series(base, 30, [100.0 + i for i in range(30)])

    result = run_backtest("Test", "ASSET", signal_scores, prices, forward_window_days=20)
    assert result.skipped_dates == 1
    assert result.sample_size == 1


def test_run_backtest_empty_signal_list_returns_empty_result():
    result = run_backtest("Test", "ASSET", [], [], forward_window_days=20)
    assert result.sample_size == 0
    assert result.correlation is None


def test_interpretation_flags_small_sample_size():
    result = run_backtest("Test", "ASSET", [(date(2020, 1, 1), 50.0)], [(date(2020, 1, 1), 100.0), (date(2020, 1, 21), 105.0)], forward_window_days=20)
    assert "too few" in result.interpretation().lower()


def test_interpretation_flags_negative_correlation_direction():
    """Same explicit-anchor-point construction as the positive-correlation
    test above, but with the relationship inverted: higher signal score
    precedes a SMALLER (more negative) forward return."""
    base = date(2020, 1, 1)
    signal_scores = []
    prices = []
    for i in range(20):
        as_of = base + timedelta(days=i * 30)
        forward = as_of + timedelta(days=20)
        start_price = 100.0
        end_price = start_price * (1.0 - (i + 1) / 100.0)  # always positive: price falls by at most 20%
        prices.append((as_of, start_price))
        prices.append((forward, end_price))
        signal_scores.append((as_of, float(i)))
    prices.sort(key=lambda t: t[0])

    result = run_backtest("Test", "ASSET", signal_scores, prices, forward_window_days=20)
    assert result.correlation < -0.9
    assert "worse returns" in result.interpretation().lower()


def test_to_dict_serializes_all_fields():
    base = date(2020, 1, 1)
    signal_scores = [(base + timedelta(days=i * 30), float(i)) for i in range(15)]
    prices = [(base + timedelta(days=i), 100.0 + i * 0.5) for i in range(500)]
    result = run_backtest("Test", "ASSET", signal_scores, prices)
    d = result.to_dict()
    assert d["sample_size"] == 15
    assert "interpretation" in d
    assert "correlation" in d


# --- windows_overlap detection ---

def test_windows_overlap_true_when_step_smaller_than_forward_window():
    """
    Regression test for a real methodological gap caught via live use:
    a user ran --step-days 7 with the default --forward-days 20, meaning
    consecutive 20-day return windows overlapped by 13 days — the
    resulting 'samples' were not statistically independent, but nothing
    flagged this, so the significance threshold looked more solid than
    it actually was.
    """
    base = date(2021, 8, 10)
    signal_scores = [(base + timedelta(days=i * 7), float(i % 5)) for i in range(50)]
    prices = [(base + timedelta(days=i), 400.0 + (i % 30)) for i in range(500)]
    result = run_backtest("Test", "SPY", signal_scores, prices, forward_window_days=20)
    assert result.windows_overlap is True
    assert result.avg_gap_days == 7.0
    assert "CAVEAT" in result.interpretation()
    assert "NOT statistically independent" in result.interpretation()


def test_windows_overlap_false_when_step_at_or_above_forward_window():
    base = date(2021, 8, 10)
    signal_scores = [(base + timedelta(days=i * 30), float(i % 5)) for i in range(15)]
    prices = [(base + timedelta(days=i), 400.0 + (i % 30)) for i in range(500)]
    result = run_backtest("Test", "SPY", signal_scores, prices, forward_window_days=20)
    assert result.windows_overlap is False
    assert "CAVEAT" not in result.interpretation()


def test_windows_overlap_none_for_insufficient_data_points():
    result = run_backtest("Test", "SPY", [], [], forward_window_days=20)
    assert result.windows_overlap is None
    assert result.avg_gap_days is None


def test_avg_gap_days_computed_correctly_for_irregular_spacing():
    base = date(2021, 8, 10)
    # Irregular gaps: 5, 10, 15 days -> average 10
    signal_scores = [(base, 1.0), (base + timedelta(days=5), 2.0),
                      (base + timedelta(days=15), 3.0), (base + timedelta(days=30), 4.0)]
    prices = [(base + timedelta(days=i), 100.0 + i) for i in range(200)]
    result = run_backtest("Test", "SPY", signal_scores, prices, forward_window_days=20)
    assert result.avg_gap_days == 10.0
