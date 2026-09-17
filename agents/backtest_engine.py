"""
Backtest engine — correlation validation between a signal's historical
bias_score and the asset's ACTUAL subsequent price return.

Per an explicit scoping decision: this platform never places trades or
sizes positions, so "backtesting" here means signal validation, not P&L
simulation — did more bullish readings historically precede better
subsequent returns than more bearish readings? This is the same
"information coefficient" concept quant researchers use to validate a
factor before ever trading on it.

Deliberately signal-agnostic: this module knows nothing about Seasonality,
VIX, or any specific department — it just takes a list of
(date, bias_score) pairs someone else computed, and a price series, and
tells you how well they lined up. Every specific signal (Seasonality,
Institutional Market Regime components, eventually Macro survey stats)
plugs into this SAME engine rather than each reinventing its own
correlation math — see docs/ARCHITECTURE_BACKTESTING.md for which
signals are wired in so far and why.

Uses Spearman RANK correlation (via a from-scratch rank transform + the
existing agents.risk_calculations.pearson_correlation — Spearman IS
Pearson correlation computed on ranks) rather than adding scipy as a new
dependency, matching this platform's established "pure Python, no heavy
new dependencies" convention (agents/risk_calculations.py already
hand-rolls VaR/drawdown/correlation the same way). Statistical
significance uses a standard large-sample normal approximation
(|r| > z/sqrt(n-1)) rather than a from-scratch t-distribution CDF —
honestly labeled as an approximation, most accurate for n >= ~30.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Tuple

from .risk_calculations import pearson_correlation


def _rank_transform(values: List[float]) -> List[float]:
    """
    Average-rank transform (ties share the mean of their ranks) — the
    standard method for computing Spearman correlation via Pearson on
    ranks. Ranks are 1-indexed, ascending (smallest value -> rank 1).
    """
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-indexed
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(a: List[float], b: List[float]) -> Optional[float]:
    """Spearman rank correlation — robust to outliers and non-linear-but-
    monotonic relationships, the standard choice for this kind of signal
    validation. Returns None under the same conditions
    agents.risk_calculations.pearson_correlation does (fewer than 2 points,
    or zero variance in either series)."""
    if len(a) != len(b) or len(a) < 2:
        return None
    return pearson_correlation(_rank_transform(a), _rank_transform(b))


def approximate_significance_threshold(n: int, confidence_level: float = 0.95) -> Optional[float]:
    """
    Rough two-tailed significance threshold for a correlation coefficient,
    using the large-sample normal approximation |r| > z / sqrt(n - 1).
    HONEST LIMITATION: accurate for n >= ~30; for smaller samples this
    UNDERSTATES the true threshold somewhat (a real t-distribution has
    fatter tails at small n), so treat a correlation only modestly above
    this threshold with extra caution when the sample is small. This is a
    deliberate approximation rather than a from-scratch t-distribution CDF
    — see this module's docstring for why scipy wasn't added just for this.
    """
    if n < 3:
        return None
    z = 1.96 if abs(confidence_level - 0.95) < 1e-9 else 2.576  # 95% or 99% two-tailed
    return z / ((n - 1) ** 0.5)


@dataclass
class BacktestDataPoint:
    as_of_date: date
    signal_score: float                    # -100..+100, whatever the signal function returned
    forward_return_pct: Optional[float]    # % price change from as_of_date to as_of_date + forward_window_days


@dataclass
class BacktestResult:
    signal_name: str
    asset: str
    forward_window_days: int
    sample_size: int
    correlation: Optional[float] = None
    significance_threshold: Optional[float] = None
    likely_significant: Optional[bool] = None
    data_points: List[BacktestDataPoint] = field(default_factory=list)
    skipped_dates: int = 0    # dates where the signal or price data wasn't available — never estimated, just excluded
    windows_overlap: Optional[bool] = None    # True if consecutive forward-return windows share days (autocorrelated samples)
    avg_gap_days: Optional[float] = None       # average calendar days between consecutive as_of_dates

    def interpretation(self) -> str:
        if self.sample_size < 10:
            return (
                f"Only {self.sample_size} usable data point(s) — too few to draw any real "
                f"conclusion. Widen the date range or check for data gaps."
            )
        if self.correlation is None:
            return "Correlation could not be computed (no variance in the signal or the returns)."
        direction = "positive (bullish readings tended to precede better returns)" if self.correlation > 0 \
            else "negative (bullish readings tended to precede WORSE returns — worth real scrutiny)" if self.correlation < 0 \
            else "exactly zero"
        sig_note = ""
        if self.likely_significant is True:
            sig_note = " This exceeds the rough significance threshold for this sample size."
        elif self.likely_significant is False:
            sig_note = " This does NOT clearly exceed the rough significance threshold for this sample size — could plausibly be noise."
        overlap_note = ""
        if self.windows_overlap:
            overlap_note = (
                f" CAVEAT: consecutive test dates are only ~{self.avg_gap_days:.0f} days apart, closer "
                f"together than the {self.forward_window_days}-day forward window — their return windows "
                f"overlap and share days, so these samples are NOT statistically independent. The "
                f"significance threshold above assumes independence, so it is understating the true bar "
                f"for genuine significance here; treat any 'likely significant' reading with real "
                f"skepticism, and prefer a wider --step-days (at or above the forward window) for a "
                f"cleaner, if smaller, test."
            )
        return (
            f"{self.signal_name} vs. {self.asset}'s {self.forward_window_days}-day forward return: "
            f"correlation {self.correlation:+.3f} over {self.sample_size} data points, direction is "
            f"{direction}.{sig_note}{overlap_note}"
        )

    def to_dict(self) -> dict:
        return {
            "signal_name": self.signal_name,
            "asset": self.asset,
            "forward_window_days": self.forward_window_days,
            "sample_size": self.sample_size,
            "correlation": self.correlation,
            "significance_threshold": self.significance_threshold,
            "likely_significant": self.likely_significant,
            "skipped_dates": self.skipped_dates,
            "windows_overlap": self.windows_overlap,
            "avg_gap_days": self.avg_gap_days,
            "interpretation": self.interpretation(),
        }


def _forward_return(price_history_oldest_first: List[Tuple[date, float]], as_of_date: date, window_days: int) -> Optional[float]:
    """
    % price change from the close ON OR BEFORE as_of_date to the close
    approximately `window_days` calendar days later (using the nearest
    available trading day, since markets are closed weekends/holidays).
    Returns None if either endpoint isn't in the price history — never
    interpolated or estimated.
    """
    start_price = None
    start_idx = None
    for i, (d, price) in enumerate(price_history_oldest_first):
        if d <= as_of_date:
            start_price = price
            start_idx = i
        else:
            break
    if start_price is None or start_idx is None:
        return None

    target_date = as_of_date + timedelta(days=window_days)
    end_price = None
    for d, price in price_history_oldest_first[start_idx:]:
        if d >= target_date:
            end_price = price
            break
    if end_price is None:
        return None

    if start_price == 0:
        return None
    return ((end_price - start_price) / start_price) * 100.0


def run_backtest(
    signal_name: str,
    asset: str,
    signal_scores: List[Tuple[date, float]],
    price_history_oldest_first: List[Tuple[date, float]],
    forward_window_days: int = 20,
) -> BacktestResult:
    """
    signal_scores: list of (as_of_date, bias_score) the caller already
    computed — this engine does NOT know how to compute any signal
    itself, it only validates one.
    price_history_oldest_first: list of (date, close) for the asset,
    oldest first.
    forward_window_days: how many CALENDAR days ahead to measure the
    return over (default 20, roughly a trading month).

    Never fabricates a data point: any (date, signal_score) whose forward
    return can't be found in the price history is simply excluded, and
    counted in skipped_dates.
    """
    data_points: List[BacktestDataPoint] = []
    skipped = 0

    for as_of_date, score in signal_scores:
        fwd_return = _forward_return(price_history_oldest_first, as_of_date, forward_window_days)
        if fwd_return is None:
            skipped += 1
            continue
        data_points.append(BacktestDataPoint(as_of_date=as_of_date, signal_score=score, forward_return_pct=fwd_return))

    scores = [dp.signal_score for dp in data_points]
    returns = [dp.forward_return_pct for dp in data_points]
    correlation = spearman_correlation(scores, returns) if len(data_points) >= 2 else None

    threshold = approximate_significance_threshold(len(data_points))
    likely_significant = None
    if correlation is not None and threshold is not None:
        likely_significant = abs(correlation) > threshold

    # Overlap detection: if consecutive test dates are spaced closer
    # together than the forward-return window, their windows share days
    # and the "samples" are not statistically independent — the
    # significance threshold above assumes independence, so it
    # understates the true bar for genuine significance in that case.
    # See BacktestResult.interpretation() for the caveat this produces.
    avg_gap_days = None
    windows_overlap = None
    if len(data_points) >= 2:
        sorted_dates = sorted(dp.as_of_date for dp in data_points)
        gaps = [(sorted_dates[i + 1] - sorted_dates[i]).days for i in range(len(sorted_dates) - 1)]
        if gaps:
            avg_gap_days = sum(gaps) / len(gaps)
            windows_overlap = avg_gap_days < forward_window_days

    return BacktestResult(
        signal_name=signal_name, asset=asset, forward_window_days=forward_window_days,
        sample_size=len(data_points), correlation=round(correlation, 4) if correlation is not None else None,
        significance_threshold=round(threshold, 4) if threshold is not None else None,
        likely_significant=likely_significant, data_points=data_points, skipped_dates=skipped,
        windows_overlap=windows_overlap, avg_gap_days=round(avg_gap_days, 1) if avg_gap_days is not None else None,
    )
