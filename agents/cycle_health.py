"""
Cycle Health.

Per an explicit later request: this platform's existing error handling
already logs "N of M watchlist entries failed this cycle" — but that only
counts HARD CRASHES (exceptions). It does NOT catch the more likely
failure mode given this platform's own design philosophy of "never crash,
always degrade gracefully": everything completing SUCCESSFULLY but
silently returning near-zero confidence across most or all entries,
because e.g. a FRED API key expired, a connector's host got blocked by a
network policy change, or a shared config value broke. A crash-only check
would show "0 of 357 failed" in exactly that scenario — technically true,
dangerously misleading.

This module distinguishes NORMAL, EXPECTED partial degradation (a handful
of tickers with genuinely bad/missing data this cycle — routine in any
live system pulling from real external sources) from a SYSTEMIC issue
(most or all entries degraded at once — almost always a single shared
root cause, not independent per-asset problems).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# A result with no error but confidence below this is counted as
# "degraded" — near-zero confidence, not just "somewhat uncertain."
DEGRADED_CONFIDENCE_THRESHOLD = 10.0

# Percentage-of-cycle thresholds above which a pattern stops looking like
# routine per-asset noise and starts looking like one shared root cause.
# Errors get a lower threshold than degradation since a hard crash is a
# more unusual, more alarming event than a data source returning nothing
# useful (which happens routinely for individual tickers).
SYSTEMIC_ERROR_PCT = 25.0
SYSTEMIC_DEGRADATION_PCT = 50.0


@dataclass
class CycleHealthResult:
    total_entries: int
    error_count: int              # hard crashes (exceptions)
    degraded_count: int           # completed successfully, but confidence < DEGRADED_CONFIDENCE_THRESHOLD
    healthy_count: int
    is_systemic_issue: bool = False
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_entries": self.total_entries,
            "error_count": self.error_count,
            "degraded_count": self.degraded_count,
            "healthy_count": self.healthy_count,
            "is_systemic_issue": self.is_systemic_issue,
            "reasons": self.reasons,
        }


def assess_cycle_health(results: List[Dict[str, Any]]) -> CycleHealthResult:
    """
    results: the exact list scripts.run_daily_cycle.run_cycle() returns —
    each entry either has "error": None plus a "confidence_score", or
    "error": <message> with no confidence_score (a hard crash).

    Returns a healthy, zero-entry result for an empty list — never a
    fabricated "systemic issue" flag from nothing to assess.
    """
    total = len(results)
    if total == 0:
        return CycleHealthResult(total_entries=0, error_count=0, degraded_count=0, healthy_count=0)

    error_count = sum(1 for r in results if r.get("error") is not None)
    degraded_count = sum(
        1 for r in results
        if r.get("error") is None and r.get("confidence_score", 0.0) < DEGRADED_CONFIDENCE_THRESHOLD
    )
    healthy_count = total - error_count - degraded_count

    reasons: List[str] = []
    is_systemic = False

    error_pct = (error_count / total) * 100.0
    degraded_pct = (degraded_count / total) * 100.0

    if error_pct >= SYSTEMIC_ERROR_PCT:
        is_systemic = True
        reasons.append(
            f"{error_count} of {total} entries ({error_pct:.0f}%) hard-crashed this cycle — "
            f"check logs for a shared root cause (a broken connector, a bad config change) "
            f"rather than {error_count} independent per-asset bugs"
        )

    if degraded_pct >= SYSTEMIC_DEGRADATION_PCT:
        is_systemic = True
        reasons.append(
            f"{degraded_count} of {total} entries ({degraded_pct:.0f}%) completed with "
            f"near-zero confidence (<{DEGRADED_CONFIDENCE_THRESHOLD:.0f}/100) — this pattern usually "
            f"means one shared cause (an expired API key, a blocked network host, a broken shared "
            f"data source) rather than {degraded_count} independent per-asset data problems"
        )

    return CycleHealthResult(
        total_entries=total, error_count=error_count, degraded_count=degraded_count,
        healthy_count=healthy_count, is_systemic_issue=is_systemic, reasons=reasons,
    )
