from agents.speculative_positioning_analysis import (
    net_positions_series, latest_weekly_change, percentile_rank,
    classify_extreme_percentile, classify_momentum_signal,
)


def _row(long_, short_, date="2026-07-01"):
    return {"noncomm_long": str(long_), "noncomm_short": str(short_), "report_date": date}


# --- net_positions_series ---

def test_net_positions_series_basic():
    history = [_row(120000, 80000), _row(100000, 90000)]
    result = net_positions_series(history)
    assert result == [40000.0, 10000.0]


def test_net_positions_series_skips_malformed_rows():
    history = [_row(120000, 80000), {"noncomm_long": None}, _row(100000, 90000)]
    result = net_positions_series(history)
    assert result == [40000.0, 10000.0]


# --- latest_weekly_change ---

def test_latest_weekly_change_positive_when_building():
    history = [_row(120000, 80000), _row(100000, 90000)]  # net: 40000 vs 10000
    assert latest_weekly_change(history) == 30000.0


def test_latest_weekly_change_negative_when_reducing():
    history = [_row(90000, 100000), _row(100000, 80000)]  # net: -10000 vs 20000
    assert latest_weekly_change(history) == -30000.0


def test_latest_weekly_change_none_with_insufficient_history():
    assert latest_weekly_change([_row(100000, 80000)]) is None


# --- percentile_rank ---

def test_percentile_rank_current_is_highest():
    # newest-first: current=50000 is the max across the window
    history = [_row(130000, 80000), _row(100000, 90000), _row(95000, 92000)]
    result = percentile_rank(history)
    assert result == 100.0


def test_percentile_rank_current_is_lowest_exact():
    history = [_row(90000, 100000), _row(100000, 80000), _row(105000, 75000)]
    # nets: -10000, 20000, 30000 -> current (-10000) is <= only itself -> 1/3
    result = percentile_rank(history)
    assert abs(result - (100.0 / 3)) < 0.01


def test_percentile_rank_none_with_insufficient_history():
    assert percentile_rank([_row(100000, 80000)]) is None


def test_percentile_rank_ties_counted_at_or_below():
    history = [_row(100000, 80000), _row(100000, 80000)]  # both nets equal: 20000, 20000
    result = percentile_rank(history)
    assert result == 100.0  # current <= both (including itself) -> 2/2


# --- classify_extreme_percentile ---

def test_classify_extreme_bullish():
    assert classify_extreme_percentile(90.0) == "extreme_bullish"
    assert classify_extreme_percentile(85.0) == "extreme_bullish"


def test_classify_extreme_bearish():
    assert classify_extreme_percentile(10.0) == "extreme_bearish"
    assert classify_extreme_percentile(15.0) == "extreme_bearish"


def test_classify_extreme_neutral_band():
    assert classify_extreme_percentile(50.0) is None
    assert classify_extreme_percentile(16.0) is None
    assert classify_extreme_percentile(84.0) is None


def test_classify_extreme_none_input():
    assert classify_extreme_percentile(None) is None


# --- classify_momentum_signal ---

def test_momentum_continuation_when_weekly_agrees_with_trend():
    # trend positive (building over weeks), weekly change also positive and large
    result = classify_momentum_signal(trend_score=40.0, weekly_change=15000.0, current_net_position=100000.0)
    assert result == "continuation"


def test_momentum_reversal_watch_when_weekly_opposes_trend():
    result = classify_momentum_signal(trend_score=40.0, weekly_change=-15000.0, current_net_position=100000.0)
    assert result == "reversal_watch"


def test_momentum_stable_when_weekly_change_too_small():
    result = classify_momentum_signal(trend_score=40.0, weekly_change=500.0, current_net_position=100000.0)
    assert result == "stable"


def test_momentum_insufficient_data_when_any_input_missing():
    assert classify_momentum_signal(None, 1000.0, 100000.0) == "insufficient_data"
    assert classify_momentum_signal(40.0, None, 100000.0) == "insufficient_data"
    assert classify_momentum_signal(40.0, 1000.0, None) == "insufficient_data"
