"""
Score momentum (spec section 3) — built entirely on data
database/report_store.py already captures (every trade_decisions row is
timestamped with both generated_at and recorded_at), so no schema change
beyond the trade_decisions table itself (database/schema.py) was needed
for this.

Momentum classification thresholds are calibrated directly off the spec's
own worked examples:
    79 -> 76  (-3)   Stable
    79 -> 61  (-18)  Weakening
    79 -> 42  (-37)  Major deterioration
    95 -> 97  (+2)   Strengthening
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.trade_decision import Momentum, ScoreMomentum

STRENGTHENING_MIN_DELTA = 0.01   # any positive move
STABLE_MIN_DELTA = -5.0          # 0 down to -5 is still "stable"
WEAKENING_MIN_DELTA = -25.0      # -5 down to -25 is "weakening"
# anything <= -25 is "major_deterioration"


def _classify(delta: Optional[float]) -> Momentum:
    if delta is None:
        return Momentum.INSUFFICIENT_HISTORY
    if delta > STRENGTHENING_MIN_DELTA:
        return Momentum.STRENGTHENING
    if delta >= STABLE_MIN_DELTA:
        return Momentum.STABLE
    if delta > WEAKENING_MIN_DELTA:
        return Momentum.WEAKENING
    return Momentum.MAJOR_DETERIORATION


def _parse_ts(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _closest_reading_before(
    history: List[Dict[str, Any]], score_field: str, cutoff: datetime,
) -> Optional[float]:
    """
    history: newest-first list of trade_decisions rows (as returned by
    ReportStore.get_trade_decisions). Returns the score_field value of the
    reading closest to (and at or before) `cutoff`, or the oldest available
    reading if every row is newer than cutoff (best-effort for thin history
    rather than returning None and losing the window entirely).
    """
    candidates = [(row, _parse_ts(row["recorded_at"])) for row in history]
    at_or_before = [row for row, ts in candidates if ts <= cutoff]
    if at_or_before:
        return at_or_before[0][score_field]  # newest-first -> first match is closest to cutoff
    if candidates:
        return candidates[-1][0][score_field]  # only newer-than-cutoff data exists; use the oldest we have
    return None


def compute_score_momentum(
    history: List[Dict[str, Any]], score_field: str, current_score: float, now: Optional[datetime] = None,
) -> ScoreMomentum:
    """
    history: newest-first rows from ReportStore.get_trade_decisions(asset_or_theme=...),
        NOT including the reading currently being evaluated (call this
        before saving the new trade_decisions row, or filter it out).
    score_field: one of "fundamental_score", "technical_score", "risk_score", "overall_score".
    """
    now = now or datetime.now(timezone.utc)

    if not history:
        return ScoreMomentum(momentum=Momentum.INSUFFICIENT_HISTORY)

    previous_score = history[0][score_field]  # most recent prior reading

    change_1h = _delta(history, score_field, now - timedelta(hours=1), current_score)
    change_4h = _delta(history, score_field, now - timedelta(hours=4), current_score)
    change_24h = _delta(history, score_field, now - timedelta(hours=24), current_score)
    change_weekly = _delta(history, score_field, now - timedelta(days=7), current_score)

    step_delta = current_score - previous_score
    momentum = _classify(step_delta)

    return ScoreMomentum(
        previous_score=previous_score,
        change_1h=change_1h,
        change_4h=change_4h,
        change_24h=change_24h,
        change_weekly=change_weekly,
        momentum=momentum,
    )


def _delta(history: List[Dict[str, Any]], score_field: str, cutoff: datetime, current_score: float) -> Optional[float]:
    past = _closest_reading_before(history, score_field, cutoff)
    if past is None:
        return None
    return round(current_score - past, 1)


def explain_momentum(momentum: Momentum, catalysts: List[str], risks: List[str]) -> List[str]:
    """
    Section 3's "the AI should explain WHY the score changed" — pulled from
    whatever this cycle's TradeDecision already flagged as catalysts/risks
    (populated by agents/chief_trade_decision_officer.py from the
    underlying department reports), so every explanation is traceable back
    to a specific department's evidence rather than invented after the fact.
    """
    if momentum in (Momentum.WEAKENING, Momentum.MAJOR_DETERIORATION):
        return risks[:3]
    if momentum == Momentum.STRENGTHENING:
        return catalysts[:3]
    return []
