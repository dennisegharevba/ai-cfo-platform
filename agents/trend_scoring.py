"""
Shared "compare oldest to newest observation in a fetched window" trend
scoring, used by any agent that reads a time-series history (FRED-shaped
data for macro/bond/equity fundamentals, or any other {"value": ...}-shaped
series).

Originally lived inside chief_macro_officer.py as a private helper shared
by direct import with chief_bond_strategist.py (two consumers). Chief
Equity Analyst (Phase 4) makes three, which is this project's own trigger
point for promoting a helper to a shared module — see docs/ARCHITECTURE_PHASE2.md.
"""

from __future__ import annotations

from typing import List, Optional


def percent_change_score(
    values: List[float],
    lower_is_bullish: bool = False,
    normalization_pct: float = 5.0,
) -> Optional[float]:
    """
    Core scoring math: percent change from the last (oldest) to first
    (newest) value in a newest-first list, normalized to -100..+100.

    normalization_pct: the percent swing treated as a "strong" (+/-100)
    signal. Macro series (CPI, unemployment) default to 5%; noisier series
    should pass a wider band (see agents.positioning_scoring's 20% band for
    COT positioning, expressed independently since it also needs the
    open-interest-relative extremity check).

    Returns None if there aren't at least 2 values to compare.
    """
    if len(values) < 2:
        return None

    latest = values[0]
    earliest = values[-1]
    if earliest == 0:
        return None

    pct_change = (latest - earliest) / abs(earliest) * 100
    normalized = max(-100.0, min(100.0, (pct_change / normalization_pct) * 100))
    return -normalized if lower_is_bullish else normalized


def series_trend_score(
    history: List[dict],
    lower_is_bullish: bool = False,
    normalization_pct: float = 5.0,
    value_key: str = "value",
) -> Optional[float]:
    """
    Extract `value_key` from each entry in a newest-first history list
    (skipping any that don't parse as a float) and score the trend via
    percent_change_score.

    value_key defaults to "value" (the FRED connector's shape). Pass e.g.
    value_key="open_interest" for connectors that use a different field name.
    """
    values = []
    for obs in history:
        raw = obs.get(value_key)
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue

    return percent_change_score(values, lower_is_bullish=lower_is_bullish, normalization_pct=normalization_pct)
