from agents.technical_indicators import rsi, macd_histogram, sma, trend_score


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
