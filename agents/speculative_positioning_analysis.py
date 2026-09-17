"""
Speculative (Non-Commercial / Large Speculator) COT positioning analysis.

Per an explicit later decision, Commercial Traders were removed as a
directional input to the Chief Commodity/FX Analyst entirely — Commercial
positioning no longer influences bias, confidence, or the overall market
score anywhere in the platform's main scoring pipeline. Primary emphasis
is now on Non-Commercial Traders (Large Speculators), on the reasoning
that they're more representative of trend-following institutional capital
that drives medium- to long-term price movements. See
docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md for the full account,
including what stayed unchanged (the separate Trade Decision Engine's own
commercial/speculative divergence check, kept by explicit user choice).

This module adds the analysis the upgrade asked for, on top of the
existing `agents.positioning_scoring.net_position_trend_score` (which
already computes an overall multi-week TREND and is reused here, not
duplicated):
    - Weekly (week-over-week) momentum in Non-Commercial net positioning
    - A percentile rank of the current net position against the fetched
      history window, to flag "positioning extremes" in that speculator
      base's own recent behavior
    - A continuation/reversal classification, combining the multi-week
      trend with the latest weekly move

Honest limitation: `percentile_rank` below is a WITHIN-FETCHED-WINDOW
percentile (typically 8 weeks — see connectors.cot_connector.CotConnector's
default), not a multi-year historical percentile. A true multi-year
percentile would need the connector to fetch (and the integrity manager to
cache) a much larger history window, which isn't built here — this is
flagged explicitly rather than presented as a longer-history calculation
it isn't. Widening the window is a config change
(`weeks_history=` on `CotConnector`) with no logic changes needed here.
"""

from __future__ import annotations

from typing import List, Optional

from .positioning_scoring import _net_position

# Percentile thresholds (within the fetched window) for calling current
# positioning "extreme" in either direction.
EXTREME_BULLISH_PERCENTILE = 85.0
EXTREME_BEARISH_PERCENTILE = 15.0

# A weekly (week-over-week) change is only treated as meaningful — worth
# calling "continuation" or "reversal_watch" — if it's at least this
# fraction of the CURRENT net position's own magnitude. Below this, the
# weekly move is noise relative to the position's size.
MEANINGFUL_WEEKLY_CHANGE_FRACTION = 0.03


def net_positions_series(
    history: List[dict], long_key: str = "noncomm_long", short_key: str = "noncomm_short",
) -> List[float]:
    """Net (long - short) position for every valid week in the fetched
    history, newest-first (matching connectors.cot_connector.CotConnector's
    convention). Rows that don't parse are silently skipped."""
    return [n for n in (_net_position(row, long_key, short_key) for row in history) if n is not None]


def latest_weekly_change(history: List[dict], long_key: str = "noncomm_long", short_key: str = "noncomm_short") -> Optional[float]:
    """
    Raw week-over-week change in net position (most recent week minus the
    week before it), in contracts — a direct read on whether speculative
    positioning is actively BUILDING, REDUCING, or UNWINDING right now,
    distinct from net_position_trend_score's longer multi-week trend.

    Returns None if there aren't at least 2 valid weekly readings.
    """
    nets = net_positions_series(history, long_key, short_key)
    if len(nets) < 2:
        return None
    return nets[0] - nets[1]


def percentile_rank(history: List[dict], long_key: str = "noncomm_long", short_key: str = "noncomm_short") -> Optional[float]:
    """
    Percentile rank (0-100) of the CURRENT (most recent) net position
    within the fetched history window. 100 means the current reading is
    the highest (most net-long) in the window; 0 means the lowest (most
    net-short). See module docstring for the "within fetched window, not
    multi-year" caveat.

    Returns None if there's only one (or zero) valid readings — a
    percentile needs something to rank against.
    """
    nets = net_positions_series(history, long_key, short_key)
    if len(nets) < 2:
        return None

    current = nets[0]
    count_at_or_below = sum(1 for n in nets if n <= current)
    return (count_at_or_below / len(nets)) * 100.0


def classify_extreme_percentile(percentile: Optional[float]) -> Optional[str]:
    """"extreme_bullish" / "extreme_bearish" / None, from a percentile_rank() result."""
    if percentile is None:
        return None
    if percentile >= EXTREME_BULLISH_PERCENTILE:
        return "extreme_bullish"
    if percentile <= EXTREME_BEARISH_PERCENTILE:
        return "extreme_bearish"
    return None


def classify_momentum_signal(
    trend_score: Optional[float], weekly_change: Optional[float], current_net_position: Optional[float],
) -> str:
    """
    Combine the multi-week trend (net_position_trend_score) with the
    latest weekly move to classify what's happening RIGHT NOW:

        "continuation"      — weekly move agrees with the broader trend's
                               direction and is large enough to matter —
                               speculative positioning is building in the
                               same direction as the established trend.
        "reversal_watch"     — weekly move meaningfully OPPOSES the broader
                               trend — a potential early sign the trend is
                               stalling or reversing, worth flagging even
                               though one week isn't proof of a reversal.
        "stable"             — weekly move is too small (relative to the
                               current position's size) to read as either.
        "insufficient_data"  — any required input is missing.
    """
    if trend_score is None or weekly_change is None or current_net_position is None:
        return "insufficient_data"

    threshold = max(abs(current_net_position) * MEANINGFUL_WEEKLY_CHANGE_FRACTION, 1.0)
    if abs(weekly_change) < threshold:
        return "stable"

    same_direction = (trend_score >= 0) == (weekly_change >= 0)
    return "continuation" if same_direction else "reversal_watch"
