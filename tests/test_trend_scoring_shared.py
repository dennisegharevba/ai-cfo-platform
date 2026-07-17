from agents.trend_scoring import percent_change_score, series_trend_score


def test_percent_change_score_rising_values_lower_is_bullish_false():
    score = percent_change_score([110, 105, 100], lower_is_bullish=False)
    assert score is not None
    assert score > 0


def test_percent_change_score_rising_values_lower_is_bullish_true():
    score = percent_change_score([110, 105, 100], lower_is_bullish=True)
    assert score is not None
    assert score < 0


def test_percent_change_score_insufficient_values():
    assert percent_change_score([100], lower_is_bullish=False) is None


def test_percent_change_score_zero_earliest_returns_none():
    assert percent_change_score([10, 5, 0], lower_is_bullish=False) is None


def test_percent_change_score_custom_normalization_widens_band():
    # A 10% move should hit the +/-100 cap with a 10% normalization band
    # but only be half that with a 20% band.
    tight = percent_change_score([110, 100], lower_is_bullish=False, normalization_pct=10.0)
    wide = percent_change_score([110, 100], lower_is_bullish=False, normalization_pct=20.0)
    assert tight == 100.0
    assert wide == 50.0


def test_series_trend_score_default_value_key_matches_fred_shape():
    history = [{"value": "110"}, {"value": "105"}, {"value": "100"}]
    score = series_trend_score(history, lower_is_bullish=False)
    assert score is not None
    assert score > 0


def test_series_trend_score_custom_value_key():
    history = [{"open_interest": "1200"}, {"open_interest": "1100"}, {"open_interest": "1000"}]
    score = series_trend_score(history, lower_is_bullish=False, value_key="open_interest")
    assert score is not None
    assert score > 0


def test_series_trend_score_wrong_value_key_yields_none():
    history = [{"value": "110"}, {"value": "100"}]
    score = series_trend_score(history, lower_is_bullish=False, value_key="open_interest")
    assert score is None
