"""
Technical indicator math for the Chief Technical Officer.

Deliberately implemented in pure Python (no numpy/pandas indicator
libraries) so every step is inspectable and matches textbook formulas
exactly — institutional research needs to be able to point at the formula,
not a library version. Closing prices are expected OLDEST-FIRST (standard
for time-series math), unlike this platform's connector convention of
newest-first history — see agents/chief_technical_officer.py for the
list-reversal step that bridges the two.
"""

from __future__ import annotations

from typing import List, Optional


def rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """
    Relative Strength Index, 0-100 scale, using a simple (not Wilder-smoothed)
    average of gains/losses over the most recent `period` changes — the
    textbook-simple variant, chosen for auditability over exact parity with
    any specific charting platform's smoothing convention.

    Returns None if there isn't enough history (need at least period+1 closes).
    """
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema_series(values: List[float], period: int) -> List[float]:
    """
    Exponential moving average series, seeded with a simple moving average
    of the first `period` values (standard convention). Returned series is
    aligned to values[period-1:] (i.e. shorter than the input by period-1).
    """
    if len(values) < period:
        return []

    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    ema_vals = [seed]
    for price in values[period:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return ema_vals


def macd_histogram(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[float]:
    """
    Standard MACD histogram (MACD line minus its signal line), in raw price
    units. Returns None if there isn't enough history for a stable signal
    line (need at least slow + signal closes).
    """
    if len(closes) < slow + signal:
        return None

    fast_ema = _ema_series(closes, fast)
    slow_ema = _ema_series(closes, slow)

    # fast_ema starts (slow-fast) points earlier than slow_ema; align them
    # to the same timeline before subtracting.
    offset = slow - fast
    fast_aligned = fast_ema[offset:]
    macd_line = [f - s for f, s in zip(fast_aligned, slow_ema)]

    if len(macd_line) < signal:
        return None

    signal_ema = _ema_series(macd_line, signal)
    return macd_line[-1] - signal_ema[-1]


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def trend_score(closes: List[float], short: int = 20, long: int = 50, normalization_pct: float = 5.0) -> Optional[float]:
    """
    Simple moving average crossover strength: how far the short-period SMA
    sits above/below the long-period SMA, as a percent of the long SMA,
    normalized to -100..+100 (a 5% separation is treated as a "strong" trend).
    """
    short_sma = sma(closes, short)
    long_sma = sma(closes, long)
    if short_sma is None or long_sma is None or long_sma == 0:
        return None

    pct_diff = (short_sma - long_sma) / abs(long_sma) * 100
    return max(-100.0, min(100.0, (pct_diff / normalization_pct) * 100))


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """
    Average True Range, textbook Wilder definition, in raw price units.
    All three series must be oldest-first and equal length (matching this
    module's convention throughout). True range for bar i (i>0) is the
    largest of: high-low, |high - prev_close|, |low - prev_close|; the
    first bar has no prior close, so it's excluded from the average.

    Returns None if there isn't enough history (need at least period+1 bars).
    """
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None

    true_ranges = []
    for i in range(1, n):
        high_low = highs[i] - lows[i]
        high_prev_close = abs(highs[i] - closes[i - 1])
        low_prev_close = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(high_low, high_prev_close, low_prev_close))

    if len(true_ranges) < period:
        return None

    return sum(true_ranges[-period:]) / period


def atr_expansion_pct(highs: List[float], lows: List[float], closes: List[float],
                       period: int = 14, lookback: int = 14) -> Optional[float]:
    """
    How much ATR(period) has expanded/contracted vs. its own reading
    `lookback` bars ago, as a percentage. Positive = volatility expanding
    (higher risk of large adverse moves); negative = volatility contracting.

    Returns None if there isn't enough history for both readings.
    """
    n = len(closes)
    if n < period + lookback + 1:
        return None

    current = atr(highs, lows, closes, period=period)
    past = atr(highs[:-lookback], lows[:-lookback], closes[:-lookback], period=period)
    if current is None or past is None or past == 0:
        return None

    return (current - past) / past * 100
