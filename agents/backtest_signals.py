"""
Backtest signal wrappers.

Thin adapters that compute what a signal's bias_score WOULD have been on
a given historical date — each one reuses the EXACT SAME scoring function
the live department already uses (agents.seasonality_scoring.score_seasonality,
agents.institutional_market_regime.score_vix/score_real_yield/
score_treasury_yield/score_fed_policy), never a reimplementation. Each
returns Optional[float] (-100..+100), None if data wasn't available for
that date — never fabricated.

SCOPE — what's wired in now, and what genuinely can't be yet:

    - Seasonality: zero point-in-time risk (a calendar month is always
      known, never revised) — the honest, fully-safe starting point.
    - VIX, 10Y TIPS Real Yield, 10Y Treasury Yield, Fed Funds Rate: all
      DAILY MARKET-OBSERVED series (see connectors/fred_historical.py's
      NON_REVISED_SERIES) — prices/rates, not survey statistics, so they
      are never meaningfully revised after publication. A point-in-time
      query is a courtesy here, not strictly required for correctness,
      but used anyway for consistency and because it costs nothing extra.
    - All 16 of Chief Macro Officer's own factors (CPI, Core CPI, PPI,
      Core PCE, GDP, Retail Sales, Unemployment Rate, NFP, Average Hourly
      Earnings, JOLTS, Initial Jobless Claims, Dollar Index, Credit
      Spreads, Consumer Confidence, Housing Starts, Federal Debt) — via
      macro_factor_signal(), added specifically to let the normalization
      thresholds recalibrated in
      docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md eventually be
      validated against real historical data, not just reasoned
      defensibly. This reuses connectors.fred_historical.fetch_point_in_time_history()
      (a full vintage-correct 5-observation window, matching what
      agents.chief_macro_officer._build_factor() fetches live) fed
      directly into agents.trend_scoring.series_trend_score() — the EXACT
      SAME scoring function the live factor uses, with that factor's OWN
      calibrated normalization_pct read directly from
      agents.chief_macro_officer._FACTOR_SPECS, never a second copy of
      those numbers that could drift out of sync.

DELIBERATELY NOT YET WIRED IN — genuinely harder, deferred:

    - News Sentiment — genuinely impossible with this platform's RSS-based
      connector, which has no historical headline archive. Permanently
      excluded, not just deferred.

WIRED IN, BUT NOT HERE: COT-based Swing Signal (agents/swing_signal.py) is
now backtestable too — connectors/cot_connector.py's
fetch_cot_history_range() was the missing piece this docstring used to
flag as unbuilt. Its wiring lives in agents/swing_signal_backtest.py
rather than in this file, because it's architecturally different from
every signal above: those are tested on a regular calendar grid (a value
on essentially any date), while Swing Signal is an EVENT signal (a value
only on the rare week it actually fires) — see that module's own
docstring for the full reasoning. Run via
scripts/run_swing_signal_backtest.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .seasonality_scoring import score_seasonality
from .institutional_market_regime import score_vix, score_real_yield, score_treasury_yield, score_fed_policy
from .trend_scoring import percent_change_score, series_trend_score
from . import chief_macro_officer as _cmo
from connectors.fred_historical import fetch_point_in_time_value, fetch_point_in_time_history


def seasonality_signal(asset: str, as_of_date: date) -> Optional[float]:
    """Zero point-in-time risk — a calendar month is always known."""
    result = score_seasonality(asset, as_of_date)
    if result is None:
        return None
    score, _reasoning = result
    return float(score)


def vix_signal(as_of_date: date, fred_api_key: str) -> Optional[float]:
    result = fetch_point_in_time_value("VIXCLS", fred_api_key, as_of_date)
    if result is None:
        return None
    value, _obs_date = result
    return score_vix(value)


def real_yield_signal(as_of_date: date, fred_api_key: str, lookback_days: int = 30) -> Optional[float]:
    """Monthly change in the 10Y TIPS real yield — needs two point-in-time
    queries (now, and ~lookback_days earlier)."""
    current = fetch_point_in_time_value("DFII10", fred_api_key, as_of_date)
    prior = fetch_point_in_time_value("DFII10", fred_api_key, as_of_date - timedelta(days=lookback_days))
    if current is None or prior is None:
        return None
    current_val, _ = current
    prior_val, _ = prior
    return score_real_yield((current_val - prior_val) * 100)  # percent -> bps


def treasury_yield_signal(as_of_date: date, fred_api_key: str, lookback_days: int = 7) -> Optional[float]:
    """Weekly change in the 10Y Treasury yield."""
    current = fetch_point_in_time_value("DGS10", fred_api_key, as_of_date)
    prior = fetch_point_in_time_value("DGS10", fred_api_key, as_of_date - timedelta(days=lookback_days))
    if current is None or prior is None:
        return None
    current_val, _ = current
    prior_val, _ = prior
    return score_treasury_yield((current_val - prior_val) * 100)  # percent -> bps


def fed_policy_signal(as_of_date: date, fred_api_key: str, lookback_days: int = 90) -> Optional[float]:
    """
    Fed Funds Rate trend — the live agent uses series_trend_score() over a
    full fetched history window; for a two-point historical comparison,
    this reuses the same underlying percent_change_score() math directly
    (series_trend_score is a thin wrapper around it) rather than
    reimplementing trend scoring. No tone/surprise overlay here — those
    are optional manual inputs even in the live agent (see
    agents/institutional_market_regime.py's own docstring), never
    available for a historical backtest either.

    Series, updated 2026-09-17: DFEDTARU (Federal Funds Target Range —
    Upper Limit), matching the live agent's switch away from FEDFUNDS (see
    agents/institutional_market_regime.py's docstring for the full
    reasoning) — kept in sync deliberately so a backtested Fed Policy score
    reflects the same data source the live score now does, not a stale
    comparison point. default lookback_days=90 matches
    agents.chief_macro_officer.py's own per-series fetch-window override
    for this same factor, for the same reason: DFEDTARU is a daily series
    that only actually changes a few times a year, so a short window would
    almost always read as flat.
    """
    current = fetch_point_in_time_value("DFEDTARU", fred_api_key, as_of_date)
    prior = fetch_point_in_time_value("DFEDTARU", fred_api_key, as_of_date - timedelta(days=lookback_days))
    if current is None or prior is None:
        return None
    current_val, _ = current
    prior_val, _ = prior
    # percent_change_score wants newest-first values.
    trend = percent_change_score([current_val, prior_val], lower_is_bullish=True)
    if trend is None:
        return None
    return score_fed_policy(trend)


# Every valid factor name macro_factor_signal() accepts — built directly
# from chief_macro_officer._FACTOR_SPECS, so this list can never drift out
# of sync with the live agent's own factor set.
MACRO_FACTOR_NAMES = [spec[0] for spec in _cmo._FACTOR_SPECS]


def macro_factor_signal(factor_name: str, as_of_date: date, fred_api_key: str, history_limit: int = 5) -> Optional[float]:
    """
    Backtests any ONE of Chief Macro Officer's 16 factors by name (see
    MACRO_FACTOR_NAMES for the exact valid strings — e.g. "CPI (Headline, YoY)",
    "GDP", "Initial Jobless Claims"). Fetches a vintage-correct
    5-observation history (matching what the live agent fetches) and
    scores it with agents.trend_scoring.series_trend_score() using that
    SAME factor's normalization_pct from chief_macro_officer._FACTOR_SPECS
    — never a second, potentially-drifted copy of that calibration.

    Returns None if the factor name isn't recognized, the FRED series has
    no mapping, or the point-in-time fetch fails — never fabricated.
    """
    spec = next((s for s in _cmo._FACTOR_SPECS if s[0] == factor_name), None)
    if spec is None:
        return None
    _name, key, lower_is_bullish, _weight, normalization_pct = spec

    series_id = _cmo._FRED_SERIES_IDS.get(key)
    if series_id is None:
        return None

    history = fetch_point_in_time_history(series_id, fred_api_key, as_of_date, limit=history_limit)
    if history is None:
        return None

    return series_trend_score(history, lower_is_bullish=lower_is_bullish, normalization_pct=normalization_pct)
