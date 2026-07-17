from agents.chief_macro_officer import _series_trend_score


def _history(values):
    """Build a fake FRED-style history list, newest first (matches FredConnector)."""
    return [{"value": str(v), "date": f"2026-0{i+1}-01"} for i, v in enumerate(reversed(values))][::-1]


def test_rising_series_lower_is_bullish_gives_negative_score():
    # values oldest->newest: 100 -> 110 (rising 10%)
    history = [{"value": "110"}, {"value": "105"}, {"value": "100"}]  # newest first
    score = _series_trend_score(history, lower_is_bullish=True)
    assert score is not None
    assert score < 0  # rising is bad when lower_is_bullish


def test_falling_series_lower_is_bullish_gives_positive_score():
    history = [{"value": "90"}, {"value": "95"}, {"value": "100"}]  # newest first, falling
    score = _series_trend_score(history, lower_is_bullish=True)
    assert score is not None
    assert score > 0


def test_flat_series_gives_near_zero_score():
    history = [{"value": "100"}, {"value": "100"}, {"value": "100"}]
    score = _series_trend_score(history, lower_is_bullish=True)
    assert score == 0.0


def test_insufficient_history_returns_none():
    history = [{"value": "100"}]
    assert _series_trend_score(history, lower_is_bullish=True) is None


def test_malformed_values_are_skipped_not_fatal():
    history = [{"value": "."}, {"value": "105"}, {"value": "100"}]
    score = _series_trend_score(history, lower_is_bullish=True)
    assert score is not None  # still computes from the two valid values
