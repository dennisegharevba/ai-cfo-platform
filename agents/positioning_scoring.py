"""
Shared scoring helpers for agents that interpret CFTC COT positioning data
(currently: Chief Commodity Analyst, Chief FX Analyst, Chief Sentiment Officer).

Two consumers importing this directly is fine per the project's own
convention (see docs/ARCHITECTURE_PHASE2.md's note on `_series_trend_score`);
if a third positioning-driven agent needs this later, it can still just
import from here.
"""

from __future__ import annotations

from typing import List, Optional


def _net_position(row: dict, long_key: str, short_key: str) -> Optional[float]:
    """Net position (long minus short) for one weekly COT row, for whichever
    trader category's fields are named by long_key/short_key."""
    try:
        return float(row[long_key]) - float(row[short_key])
    except (KeyError, TypeError, ValueError):
        return None


def net_position_trend_score(
    history: List[dict], long_key: str = "noncomm_long", short_key: str = "noncomm_short",
) -> Optional[float]:
    """
    Score the TREND in net positioning across a COT history window (newest
    first, as returned by connectors.cot_connector.CotConnector).

    Defaults to non-commercial (speculative) positioning — the original
    Phase 3 signal, kept as the default so existing callers are unaffected.
    Pass long_key="comm_long", short_key="comm_short" to score COMMERCIAL
    (producer/hedger) positioning instead — see
    docs/ARCHITECTURE_PHASE3.md's update note on why both matter: speculative
    positioning tends to be trend-following (useful for momentum/crowd-risk
    reads), while commercial positioning reflects real hedging exposure and
    is often read as a structural "smart money" signal moving opposite to
    the speculative crowd.

    Positive score = that category has been building net length (bullish
    positioning momentum for that category). Negative = reducing length /
    building shorts.

    A 20% swing in net position (relative to the earliest reading in the
    window) is treated as a "strong" signal, in the same spirit as
    agents.trend_scoring's default 5% threshold for macro series —
    positioning data is naturally noisier, hence the wider band.

    Returns None if there isn't enough valid history to compute a trend.
    """
    nets = [n for n in (_net_position(row, long_key, short_key) for row in history) if n is not None]
    if len(nets) < 2:
        return None

    latest = nets[0]
    earliest = nets[-1]
    denom = abs(earliest) if earliest != 0 else max(abs(latest), 1.0)

    pct_change = (latest - earliest) / denom * 100
    return max(-100.0, min(100.0, (pct_change / 20.0) * 100))


def positioning_extremity_flag(latest_row: dict, extreme_threshold_pct: float = 40.0) -> Optional[str]:
    """
    Flag when net SPECULATIVE positioning is a large share of total open
    interest — a classic "crowded trade" signal that often precedes mean
    reversion, independent of the trend direction itself.

    Deliberately speculative-only: commercials routinely run large net
    positions as a normal consequence of hedging their underlying business
    (e.g. a producer structurally short to hedge future output), so a large
    commercial position isn't itself a "crowd risk" signal the way a large
    speculative position is — it doesn't carry the same mean-reversion
    implication.

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
