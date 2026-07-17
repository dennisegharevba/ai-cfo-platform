"""
Shared scoring helpers for agents that interpret CFTC COT positioning data
(currently: Chief Commodity Analyst, Chief FX Analyst).

Two consumers importing this directly is fine per the project's own
convention (see docs/ARCHITECTURE_PHASE2.md's note on `_series_trend_score`);
if a third positioning-driven agent needs this later, it can still just
import from here.
"""

from __future__ import annotations

from typing import List, Optional


def _net_noncomm_position(row: dict) -> Optional[float]:
    """Net non-commercial (speculator) position for one weekly COT row."""
    try:
        return float(row["noncomm_long"]) - float(row["noncomm_short"])
    except (KeyError, TypeError, ValueError):
        return None


def net_position_trend_score(history: List[dict]) -> Optional[float]:
    """
    Score the TREND in net speculative positioning across a COT history
    window (newest first, as returned by connectors.cot_connector.CotConnector).

    Positive score = speculators have been building net length (bullish
    positioning momentum). Negative score = speculators have been reducing
    length / building shorts (bearish positioning momentum).

    A 20% swing in net position (relative to the earliest reading in the
    window) is treated as a "strong" signal, in the same spirit as
    agents.chief_macro_officer._series_trend_score's 5% threshold for
    macro series — positioning data is naturally noisier, hence the wider band.

    Returns None if there isn't enough valid history to compute a trend.
    """
    nets = [n for n in (_net_noncomm_position(row) for row in history) if n is not None]
    if len(nets) < 2:
        return None

    latest = nets[0]
    earliest = nets[-1]
    denom = abs(earliest) if earliest != 0 else max(abs(latest), 1.0)

    pct_change = (latest - earliest) / denom * 100
    return max(-100.0, min(100.0, (pct_change / 20.0) * 100))


def positioning_extremity_flag(latest_row: dict, extreme_threshold_pct: float = 40.0) -> Optional[str]:
    """
    Flag when net speculative positioning is a large share of total open
    interest — a classic "crowded trade" signal that often precedes mean
    reversion, independent of the trend direction itself.

    Returns "crowded_long", "crowded_short", or None.
    """
    try:
        long_ = float(latest_row["noncomm_long"])
        short_ = float(latest_row["noncomm_short"])
        oi = float(latest_row["open_interest"])
    except (KeyError, TypeError, ValueError):
        return None

    if oi <= 0:
        return None

    net_pct_of_oi = (long_ - short_) / oi * 100
    if net_pct_of_oi > extreme_threshold_pct:
        return "crowded_long"
    if net_pct_of_oi < -extreme_threshold_pct:
        return "crowded_short"
    return None
