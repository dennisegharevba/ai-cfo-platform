"""
Weekly sentiment digest — aggregates the last 7 days of Chief Sentiment
Officer reports (already persisted via database/report_store.py) into a
single summary: how many days were bullish/bearish/neutral, the average
bias and confidence over the week, and the most-repeated catalysts and
risks across the whole period.

Deliberately reuses the platform's existing persistence
(database.report_store.ReportStore) rather than adding new storage —
every report saved during normal operation already has what's needed
(bias, bias_score, confidence, catalysts, risks, recorded_at). This
module only aggregates what's already there.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WeeklyDigest:
    report_count: int
    date_range_start: str  # recorded_at of the OLDEST report in the window (ISO string, as stored)
    date_range_end: str    # recorded_at of the NEWEST report in the window
    average_bias_score: float
    average_confidence: float
    bias_day_counts: Dict[str, int] = field(default_factory=dict)  # e.g. {"bullish": 3, "neutral": 2, "bearish": 2}
    top_catalysts: List[str] = field(default_factory=list)
    top_risks: List[str] = field(default_factory=list)


def build_weekly_sentiment_digest(reports: List[Dict[str, Any]], top_n: int = 5) -> Optional[WeeklyDigest]:
    """
    reports: the output of ReportStore.get_agent_reports(department=...,
    since=..., limit=...) — newest-first, per that method's own ordering.

    Returns None (never a fabricated digest) if reports is empty — there
    is genuinely nothing to summarize, and a digest built from zero
    reports would misleadingly imply a real, quiet week rather than "no
    data was available."
    """
    if not reports:
        return None

    bias_scores = [r["bias_score"] for r in reports]
    confidences = [r["confidence"] for r in reports]
    bias_counts = Counter(r["bias"] for r in reports)

    catalyst_counter = Counter(c for r in reports for c in r.get("catalysts", []))
    risk_counter = Counter(rk for r in reports for rk in r.get("risks", []))

    # reports is newest-first (ReportStore's own ordering), so the first
    # entry is the newest, the last is the oldest, within this window.
    return WeeklyDigest(
        report_count=len(reports),
        date_range_start=reports[-1]["recorded_at"],
        date_range_end=reports[0]["recorded_at"],
        average_bias_score=round(sum(bias_scores) / len(bias_scores), 1),
        average_confidence=round(sum(confidences) / len(confidences), 1),
        bias_day_counts=dict(bias_counts),
        top_catalysts=[c for c, _count in catalyst_counter.most_common(top_n)],
        top_risks=[rk for rk, _count in risk_counter.most_common(top_n)],
    )
