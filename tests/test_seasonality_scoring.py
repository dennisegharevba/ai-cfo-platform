from datetime import date

from agents.seasonality_scoring import score_seasonality, SEASONALITY_PATTERNS


def test_gold_september_is_bullish():
    result = score_seasonality("Gold", date(2026, 9, 15))
    assert result is not None
    score, reasoning = result
    assert score > 0
    assert "wedding" in reasoning.lower() or "diwali" in reasoning.lower()


def test_natural_gas_january_is_bullish():
    result = score_seasonality("Natural Gas", date(2026, 1, 15))
    score, reasoning = result
    assert score > 0
    assert "heating" in reasoning.lower()


def test_corn_october_is_bearish():
    result = score_seasonality("Corn", date(2026, 10, 15))
    score, reasoning = result
    assert score < 0
    assert "harvest" in reasoning.lower()


def test_crude_oil_june_is_bullish():
    result = score_seasonality("WTI Crude Oil", date(2026, 6, 15))
    score, reasoning = result
    assert score > 0
    assert "driving" in reasoning.lower()


def test_sp500_september_is_bearish():
    result = score_seasonality("S&P500", date(2026, 9, 15))
    score, reasoning = result
    assert score < 0


def test_sp500_december_is_bullish():
    result = score_seasonality("S&P500", date(2026, 12, 15))
    score, reasoning = result
    assert score > 0


def test_unlisted_asset_returns_none():
    assert score_seasonality("Some Random Thing", date(2026, 9, 15)) is None


def test_every_configured_asset_has_all_12_months():
    for asset, pattern in SEASONALITY_PATTERNS.items():
        assert set(pattern.keys()) == set(range(1, 13)), f"{asset} is missing a month"


def test_every_score_is_within_moderate_bounds():
    # Seasonality is a supporting signal — scores should never approach
    # the extremes reserved for primary drivers.
    for asset, pattern in SEASONALITY_PATTERNS.items():
        for month, (score, _reasoning) in pattern.items():
            assert -50 <= score <= 50, f"{asset} month {month} score {score} exceeds moderate bounds"


def test_every_entry_has_a_nonempty_reasoning_string():
    for asset, pattern in SEASONALITY_PATTERNS.items():
        for month, (_score, reasoning) in pattern.items():
            assert isinstance(reasoning, str) and len(reasoning) > 0
