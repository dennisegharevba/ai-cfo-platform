from agents.technical_indicators import (
    rsi, macd_histogram, sma, trend_score, volatility_normalized_trend_score,
    volume_confirmation_ratio, volume_confirmation_multiplier,
)


def test_rsi_all_gains_is_100():
    closes = [100 + i for i in range(20)]  # strictly rising
    assert rsi(closes, period=14) == 100.0


def test_rsi_all_losses_is_0():
    closes = [100 - i for i in range(20)]  # strictly falling
    assert rsi(closes, period=14) == 0.0


def test_rsi_flat_prices_is_100_no_losses():
    closes = [100.0] * 20
    # no losses at all -> avg_loss == 0 -> RSI defined as 100 by this formula
    assert rsi(closes, period=14) == 100.0


def test_rsi_insufficient_history_returns_none():
    assert rsi([100, 101, 102], period=14) is None


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], period=5) == 3.0


def test_sma_insufficient_history_returns_none():
    assert sma([1, 2], period=5) is None


def test_trend_score_uptrend_is_positive():
    # short SMA period=3 over rising values will sit above long SMA period=5
    closes = [10, 11, 12, 13, 14, 15, 16, 17]
    score = trend_score(closes, short=3, long=5)
    assert score is not None
    assert score > 0


def test_trend_score_downtrend_is_negative():
    closes = [17, 16, 15, 14, 13, 12, 11, 10]
    score = trend_score(closes, short=3, long=5)
    assert score is not None
    assert score < 0


def test_trend_score_insufficient_history_returns_none():
    assert trend_score([1, 2, 3], short=20, long=50) is None


def test_macd_histogram_accelerating_uptrend_is_positive():
    # Compounding growth accelerates over time, unlike a straight line (which
    # correctly produces a ~zero histogram once MACD stabilizes, since the
    # histogram measures trend ACCELERATION, not the trend itself).
    closes = [100 * (1.01 ** i) for i in range(60)]
    hist = macd_histogram(closes, fast=12, slow=26, signal=9)
    assert hist is not None
    assert hist > 0


def test_macd_histogram_accelerating_downtrend_is_negative():
    # 200 minus a growing exponential term -> decrements grow in magnitude
    # over time, i.e. a genuinely ACCELERATING decline (the previous
    # 0.99**i formulation actually decelerates in absolute terms, since the
    # exponential term itself shrinks — worth noting since it's a subtle trap).
    closes = [200 - 100 * (1.01 ** i) for i in range(60)]
    hist = macd_histogram(closes, fast=12, slow=26, signal=9)
    assert hist is not None
    assert hist < 0


def test_macd_histogram_insufficient_history_returns_none():
    closes = [100 + i for i in range(20)]  # fewer than slow(26)+signal(9)=35
    assert macd_histogram(closes) is None


# --- volatility_normalized_trend_score: the real cross-asset-class ranking bug fix ---

def test_volatility_normalized_score_none_for_missing_volatility():
    closes = [100.0] * 30 + [105.0] * 20
    assert volatility_normalized_trend_score(closes, annualized_vol_pct=None) is None


def test_volatility_normalized_score_none_for_non_positive_volatility():
    closes = [100.0] * 30 + [105.0] * 20
    assert volatility_normalized_trend_score(closes, annualized_vol_pct=0.0) is None
    assert volatility_normalized_trend_score(closes, annualized_vol_pct=-5.0) is None


def test_volatility_normalized_score_insufficient_history_returns_none():
    closes = [100.0, 101.0, 102.0]  # far fewer than the default long=50 period
    assert volatility_normalized_trend_score(closes, annualized_vol_pct=20.0) is None


def test_volatility_normalized_score_direction_matches_trend_direction():
    uptrend = [100.0] * 30 + [105.0] * 20
    downtrend = [105.0] * 30 + [100.0] * 20
    assert volatility_normalized_trend_score(uptrend, annualized_vol_pct=20.0) > 0
    assert volatility_normalized_trend_score(downtrend, annualized_vol_pct=20.0) < 0


def test_volatility_normalized_score_correctly_ranks_the_same_move_higher_for_a_calmer_asset():
    """
    THE core regression test for the real bug found via live testing: the
    exact same price move must score as MORE significant for an asset
    with LOWER typical volatility than for one with HIGHER typical
    volatility — the opposite of what the flat-normalization trend_score()
    effectively did when comparing across genuinely different asset
    classes (see docs/ARCHITECTURE_OPPORTUNITY_SCREENER.md for the real
    live output — a screener run across equities/commodities/FX/crypto
    came back essentially 100% volatile growth stocks, not because they
    genuinely had the best opportunities, but because a flat 5% bar
    structurally favored whichever class was more volatile).
    """
    closes = [100.0] * 30 + [105.0] * 20  # identical price move for both comparisons below
    calm_asset_score = volatility_normalized_trend_score(closes, annualized_vol_pct=8.0)   # e.g. a major FX pair
    volatile_asset_score = volatility_normalized_trend_score(closes, annualized_vol_pct=50.0)  # e.g. a growth stock
    assert calm_asset_score > volatile_asset_score


def test_volatility_normalized_score_clamped_to_valid_range():
    extreme_move = [100.0] * 30 + [500.0] * 20
    score = volatility_normalized_trend_score(extreme_move, annualized_vol_pct=1.0)  # tiny vol -> would blow past 100 unclamped
    assert -100.0 <= score <= 100.0


def test_flat_normalized_trend_score_unchanged_by_the_new_function_existing():
    """trend_score() itself must behave EXACTLY as before — this is an
    additive function, not a replacement, and every existing caller
    (Chief Equity Analyst, the Trade Decision Engine) must see zero
    behavior change."""
    closes = [100.0] * 30 + [105.0] * 20
    assert trend_score(closes) == 58.82 or round(trend_score(closes), 2) == 58.82


# --- volume_confirmation_ratio / volume_confirmation_multiplier ---

def test_volume_confirmation_ratio_elevated_recent_volume():
    volumes = [2_000_000] * 5 + [1_000_000] * 45
    ratio = volume_confirmation_ratio(volumes)
    assert ratio > 1.0


def test_volume_confirmation_ratio_below_average_recent_volume():
    volumes = [500_000] * 5 + [1_000_000] * 45
    ratio = volume_confirmation_ratio(volumes)
    assert ratio < 1.0


def test_volume_confirmation_ratio_exactly_average_is_one():
    volumes = [1_000_000] * 50
    assert volume_confirmation_ratio(volumes) == 1.0


def test_volume_confirmation_ratio_none_for_insufficient_history():
    assert volume_confirmation_ratio([1_000_000] * 10) is None


def test_volume_confirmation_ratio_none_when_all_zero():
    """THE core fairness test: an instrument with no usable Yahoo volume
    (common for FX pairs) must return None, not a fabricated ratio from
    zeros — which would otherwise silently produce a ratio of 0/0 or a
    misleadingly confident-looking number from garbage data."""
    assert volume_confirmation_ratio([0.0] * 50) is None


def test_volume_confirmation_multiplier_neutral_for_none():
    """THE core fairness test for the multiplier itself: missing volume
    data must map to an EXACTLY neutral 1.0 multiplier — never a penalty.
    Penalizing an asset class for lacking Yahoo-reported volume would
    repeat, via a new mechanism, the same cross-asset-class fairness
    mistake already found and fixed for trend_score()."""
    assert volume_confirmation_multiplier(None) == 1.0


def test_volume_confirmation_multiplier_boosts_for_elevated_volume():
    assert volume_confirmation_multiplier(1.5) > 1.0


def test_volume_confirmation_multiplier_reduces_for_below_average_volume():
    assert volume_confirmation_multiplier(0.5) < 1.0


def test_volume_confirmation_multiplier_neutral_at_exactly_one():
    assert volume_confirmation_multiplier(1.0) == 1.0


def test_volume_confirmation_multiplier_capped_at_upper_bound():
    assert volume_confirmation_multiplier(10.0) == 1.15


def test_volume_confirmation_multiplier_floored_at_lower_bound():
    assert volume_confirmation_multiplier(0.0) == 0.85
