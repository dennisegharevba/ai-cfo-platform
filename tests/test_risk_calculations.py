from agents.risk_calculations import (
    daily_returns, annualized_volatility, historical_var, max_drawdown, pearson_correlation,
)


def test_daily_returns_basic():
    closes = [100, 110, 99]  # +10%, then -10%
    returns = daily_returns(closes)
    assert len(returns) == 2
    assert abs(returns[0] - 0.10) < 1e-9
    assert abs(returns[1] - (-0.10)) < 1e-9


def test_daily_returns_skips_zero_previous_price():
    closes = [0, 100, 110]
    returns = daily_returns(closes)
    assert len(returns) == 1  # the 0->100 leg is skipped (division by zero)


def test_annualized_volatility_zero_for_constant_returns():
    returns = [0.01] * 30
    vol = annualized_volatility(returns)
    # Floating-point variance math on constant input can leave tiny residue
    # (e.g. ~1e-15) depending on Python build/platform, even though the true
    # mathematical answer is exactly zero — use a tolerance, not ==.
    assert abs(vol) < 1e-9


def test_annualized_volatility_positive_for_varying_returns():
    returns = [0.01, -0.02, 0.015, -0.01, 0.02] * 6
    vol = annualized_volatility(returns)
    assert vol is not None
    assert vol > 0


def test_annualized_volatility_insufficient_data_returns_none():
    assert annualized_volatility([0.01]) is None


def test_historical_var_insufficient_data_returns_none():
    assert historical_var([0.01] * 5) is None


def test_historical_var_positive_for_realistic_returns():
    # 100 days, mostly small moves with a few large negative tail days
    returns = [0.001] * 90 + [-0.05, -0.04, -0.03, -0.06, -0.045, -0.02, -0.035, -0.025, -0.055, -0.015]
    var95 = historical_var(returns, confidence=0.95)
    assert var95 is not None
    assert var95 > 0


def test_historical_var_near_zero_for_flat_returns():
    returns = [0.0] * 50
    var95 = historical_var(returns, confidence=0.95)
    assert abs(var95) < 1e-9


def test_max_drawdown_no_decline_is_zero():
    closes = [100, 101, 102, 103, 104]
    assert abs(max_drawdown(closes)) < 1e-9


def test_max_drawdown_captures_peak_to_trough():
    closes = [100, 120, 90, 95, 110]  # peak 120 -> trough 90 = -25%
    dd = max_drawdown(closes)
    assert dd is not None
    assert abs(dd - (-25.0)) < 1e-9


def test_max_drawdown_insufficient_data_returns_none():
    assert max_drawdown([100]) is None


def test_pearson_correlation_perfectly_correlated():
    a = [0.01, 0.02, -0.01, 0.03, -0.02]
    b = [0.01, 0.02, -0.01, 0.03, -0.02]
    corr = pearson_correlation(a, b)
    assert corr is not None
    assert abs(corr - 1.0) < 1e-9


def test_pearson_correlation_perfectly_inverse():
    a = [0.01, 0.02, -0.01, 0.03, -0.02]
    b = [-0.01, -0.02, 0.01, -0.03, 0.02]
    corr = pearson_correlation(a, b)
    assert corr is not None
    assert abs(corr - (-1.0)) < 1e-9


def test_pearson_correlation_zero_variance_returns_none():
    a = [0.01, 0.01, 0.01]
    b = [0.02, 0.03, 0.01]
    assert pearson_correlation(a, b) is None


def test_pearson_correlation_insufficient_data_returns_none():
    assert pearson_correlation([0.01], [0.02]) is None
