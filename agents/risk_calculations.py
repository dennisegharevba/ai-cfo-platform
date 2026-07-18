"""
Risk calculations for the Chief Risk Officer.

Pure Python, no numpy — same philosophy as agents/technical_indicators.py:
every formula should be inspectable and match a textbook definition exactly,
since institutional risk reporting needs to be auditable, not a library
version number.

All price series are expected OLDEST-FIRST (standard for return/risk math),
matching agents/technical_indicators.py's convention — connectors store
history newest-first, so callers reverse before use (see
agents/chief_risk_officer.py's `_closes_oldest_first`).
"""

from __future__ import annotations

from typing import List, Optional

TRADING_DAYS_PER_YEAR = 252


def daily_returns(closes_oldest_first: List[float]) -> List[float]:
    """Simple (not log) daily percent returns, oldest-first, length = len(closes)-1."""
    returns = []
    for i in range(1, len(closes_oldest_first)):
        prev = closes_oldest_first[i - 1]
        if prev == 0:
            continue
        returns.append((closes_oldest_first[i] - prev) / prev)
    return returns


def _stdev(values: List[float]) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)  # sample stdev
    return variance ** 0.5


def annualized_volatility(returns: List[float], periods_per_year: int = TRADING_DAYS_PER_YEAR) -> Optional[float]:
    """Annualized volatility (%) from a list of daily returns."""
    stdev = _stdev(returns)
    if stdev is None:
        return None
    return stdev * (periods_per_year ** 0.5) * 100


def historical_var(returns: List[float], confidence: float = 0.95) -> Optional[float]:
    """
    Historical Value at Risk, as a positive percentage representing the loss
    threshold at the given confidence level (e.g. VaR95=3.2 means "on the
    worst 5% of days in this sample, the loss was at least 3.2%").

    Uses simple linear interpolation on the sorted empirical return
    distribution rather than a parametric (normal-distribution) assumption —
    more robust to fat tails, at the cost of needing enough sample points to
    be meaningful (documented in the agent's confidence scoring, not enforced
    here).
    """
    if len(returns) < 10:  # too few points for a remotely meaningful percentile
        return None

    sorted_returns = sorted(returns)
    tail_fraction = 1.0 - confidence  # e.g. 0.05 for a 95% VaR
    index = tail_fraction * (len(sorted_returns) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_returns) - 1)
    weight = index - lower
    interpolated = sorted_returns[lower] + (sorted_returns[upper] - sorted_returns[lower]) * weight

    return max(0.0, -interpolated * 100)


def max_drawdown(closes_oldest_first: List[float]) -> Optional[float]:
    """Maximum peak-to-trough decline (%) over the series, as a negative number."""
    if len(closes_oldest_first) < 2:
        return None

    peak = closes_oldest_first[0]
    worst = 0.0
    for price in closes_oldest_first:
        peak = max(peak, price)
        if peak > 0:
            drawdown = (price - peak) / peak * 100
            worst = min(worst, drawdown)
    return worst


def pearson_correlation(a: List[float], b: List[float]) -> Optional[float]:
    """Pearson correlation coefficient between two return series (aligned on their trailing overlap)."""
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[-n:], b[-n:]
    mean_a, mean_b = sum(a) / n, sum(b) / n

    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)

    if var_a == 0 or var_b == 0:
        return None
    return cov / ((var_a ** 0.5) * (var_b ** 0.5))
