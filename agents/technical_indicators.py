"""
Technical indicator math.

Originally written for the Chief Technical Officer, which was later
removed from the platform's main scoring pipeline entirely per user
request (the platform now scores purely on fundamentals, macro, and
global news/sentiment — see
docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md). This module's functions
are still used by the separate Trade Decision Engine
(agents/score_momentum.py, agents/asset_risk_officer.py's ATR-based stop
distance), which is a different feature with a different purpose and was
deliberately kept as-is.

Deliberately implemented in pure Python (no numpy/pandas indicator
libraries) so every step is inspectable and matches textbook formulas
exactly — institutional research needs to be able to point at the formula,
not a library version. Closing prices are expected OLDEST-FIRST (standard
for time-series math), unlike this platform's connector convention of
newest-first history — see agents/asset_risk_officer.py for the
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


def volatility_normalized_trend_score(
    closes: List[float], annualized_vol_pct: float, short: int = 20, long: int = 50,
) -> Optional[float]:
    """
    Same SMA-crossover-strength measure as trend_score() above, but
    normalized by the asset's OWN volatility instead of a flat percentage
    threshold.

    Found via live testing of agents/opportunity_screener.py: trend_score()'s
    flat 5% threshold structurally favors high-volatility assets when
    ranking across DIFFERENT asset classes together. A 5% SMA separation is
    a routine, unremarkable occurrence for a volatile growth stock, but a
    genuinely rare, significant one for a major FX pair — comparing both
    against the same flat bar meant a real screener run across equities,
    commodities, FX, and crypto came back essentially 100% volatile growth
    stocks, not because those genuinely had the best opportunities, but
    because the scoring method structurally couldn't score anything else
    as highly. See docs/ARCHITECTURE_OPPORTUNITY_SCREENER.md for the full
    account, including the real live output that surfaced this.

    This function instead asks "how large is this move RELATIVE TO WHAT'S
    NORMAL FOR THIS ASSET" — a move equal to the asset's own typical
    volatility over a comparable window scores 100, regardless of whether
    that asset is a calm currency pair or a volatile growth stock, making
    cross-asset-class comparison genuinely fair rather than structurally
    biased toward whichever class happens to be more volatile.

    annualized_vol_pct: the asset's own annualized volatility (%) — e.g.
        from agents.risk_calculations.annualized_volatility() computed on
        its own recent daily returns. Returns None (not a fabricated
        score) if this is missing or non-positive — never silently
        falls back to the flat-normalization behavior instead.

    Deliberately NOT a replacement for trend_score() above — that
    function is already used and tested elsewhere in this platform
    (Chief Equity Analyst, the Trade Decision Engine) for single-asset
    analysis, where cross-asset-class fairness isn't the relevant
    question; changing its default behavior there wasn't warranted by
    this finding and risks regressing verified behavior. This is a
    separate, additive function for where fair ranking ACROSS classes
    specifically matters.
    """
    short_sma = sma(closes, short)
    long_sma = sma(closes, long)
    if short_sma is None or long_sma is None or long_sma == 0:
        return None
    if annualized_vol_pct is None or annualized_vol_pct <= 0:
        return None

    pct_diff = (short_sma - long_sma) / abs(long_sma) * 100
    # Standard time-scaling convention: volatility scales with sqrt(time).
    # Scales the asset's ANNUAL volatility down to the ~`long`-period
    # window actually being compared by the SMA crossover above.
    period_vol_pct = annualized_vol_pct * ((long / 252.0) ** 0.5)
    if period_vol_pct <= 0:
        return None
    return max(-100.0, min(100.0, (pct_diff / period_vol_pct) * 100))


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


def volume_confirmation_ratio(volumes_newest_first: List[float], recent_window: int = 5, baseline_window: int = 50) -> Optional[float]:
    """
    Compares RECENT average volume against a longer-term baseline average
    — a real, well-established concept (volume should confirm a genuine
    price move; classical technical analysis, going back to Dow Theory,
    treats a move on unusually LOW volume as less reliable than the same
    move on elevated volume).

    Returns a ratio: recent average volume / baseline average volume.
    1.0 = exactly average. Above 1.0 = elevated (the move has real volume
    backing it). Below 1.0 = below-average (the move lacks volume
    confirmation).

    Returns None — never a fabricated ratio — if there isn't enough
    volume history, or if the available volume data is unusable (the
    whole baseline window is 0.0, connectors/yahoo_history_connector.py's
    own honest signal that this instrument doesn't report usable volume
    via Yahoo — true for some FX pairs and a few commodities).
    """
    if len(volumes_newest_first) < baseline_window:
        return None
    baseline_slice = volumes_newest_first[:baseline_window]
    if all(v == 0.0 for v in baseline_slice):
        return None
    baseline_avg = sum(baseline_slice) / len(baseline_slice)
    if baseline_avg <= 0:
        return None
    recent_slice = volumes_newest_first[:recent_window]
    recent_avg = sum(recent_slice) / len(recent_slice)
    return recent_avg / baseline_avg


def volume_confirmation_multiplier(volume_ratio: Optional[float]) -> float:
    """
    Converts a raw volume_confirmation_ratio() into a bounded conviction
    multiplier, for agents/opportunity_screener.py to apply on top of its
    existing conviction score.

    No usable volume data -> 1.0, exactly neutral. This is deliberate:
    penalizing an asset simply for lacking Yahoo-reported volume (common
    for FX pairs) would repeat, via a different mechanism, the same
    cross-asset-class fairness mistake already found and fixed for
    trend_score() earlier in this project (see
    volatility_normalized_trend_score()'s own docstring) — an asset class
    must never score worse merely because a data source doesn't cover it.

    Bounded to [0.85, 1.15] so a single unusual volume spike or lull can't
    dominate or wildly distort the overall conviction score — this is a
    real, but secondary, confirmation signal, not the primary driver of
    ranking. Linear within that range: ratio 1.0 (average) -> 1.0
    (neutral); ratio 2.0 (double average) -> 1.15 (the cap); ratio 0.0
    (no recent volume at all) -> 0.85 (the floor).
    """
    if volume_ratio is None:
        return 1.0
    multiplier = 1.0 + 0.15 * (volume_ratio - 1.0)
    return max(0.85, min(1.15, multiplier))
