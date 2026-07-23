"""
Institutional Relationship Engine.

Implements the upgrade requested on top of Phase 3's Chief Commodity/FX
Analyst blend: Commercial Hedgers and Large Speculators are never forced
to "pick a winner." Instead their relationship is classified, and that
classification adjusts confidence rather than direction — commercial and
speculative positioning both continue to feed the bias score exactly as
they did before (see agents/positioning_agent_base.py), but the
RELATIONSHIP between them now has its own explicit effect on how much to
trust that bias.

Three concepts live here, used by two different agents:
    - AlignmentStatus / classify_alignment / apply_confidence_adjustment
      — used by agents/positioning_agent_base.py (Chief Commodity/FX
      Analyst), where commercial vs. speculative agreement/disagreement
      is computed.
    - ExecutionReadiness / classify_execution_readiness — used by
      agents/chief_strategy_officer.py, since "is technical confirmation
      present" is a cross-department question the Strategy Officer is
      already positioned to answer (it already sees every department's
      report), not something a single positioning agent can determine on
      its own.
    - build_institutional_commentary — a plain deterministic string
      builder (no LLM), consistent with the rest of this platform's
      preference for auditable, reproducible text over generated prose.

Honest scope note: the confidence-adjustment and divergence-threshold
values below are the specific numbers given in the upgrade spec
(+15/-10/-25, 20/50 magnitude thresholds). The spec asks for these to
become adaptive based on historical testing and asset class/regime — that
full self-recalibration loop is NOT built here (it would need a
substantial backtesting/learning system of its own); these are static,
named constants you can tune by hand, not a live-learning engine. See
docs/ARCHITECTURE_INSTITUTIONAL_RELATIONSHIP_ENGINE.md for the full
reasoning and what's deferred.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from models.report import Bias, RiskLevel

# --- Alignment between commercial and speculative positioning ---


class AlignmentStatus(str, Enum):
    FULL_ALIGNMENT = "full_alignment"
    MILD_DIVERGENCE = "mild_divergence"
    STRONG_DIVERGENCE = "strong_divergence"


# Magnitude thresholds (on the same -100..+100 scale net_position_trend_score
# uses) for how strongly opposed commercial/speculative readings must be
# before being called a "divergence" at all, and before that divergence is
# escalated to "strong."
MILD_DIVERGENCE_MIN = 20.0
STRONG_DIVERGENCE_MIN = 50.0

# Confidence adjustment (percentage points on the 0-100 confidence scale),
# applied additively and clamped back to 0-100 — the exact values given in
# the upgrade spec.
CONFIDENCE_ADJUSTMENT_PCT = {
    AlignmentStatus.FULL_ALIGNMENT: 15.0,
    AlignmentStatus.MILD_DIVERGENCE: -10.0,
    AlignmentStatus.STRONG_DIVERGENCE: -25.0,
}


def classify_alignment(spec_score: Optional[float], comm_score: Optional[float]) -> Optional[AlignmentStatus]:
    """
    Classify the relationship between a speculative net-position trend
    score and a commercial net-position trend score (both from
    agents.positioning_scoring.net_position_trend_score, -100..+100).

    Same sign (or either at/near zero) -> FULL_ALIGNMENT: long-term value
    (commercials) and current participation (speculators) are not
    fighting each other.

    Opposite signs -> the average magnitude of the two readings determines
    how meaningful the conflict is: two strongly-opposed large readings is
    a real structural warning (STRONG_DIVERGENCE); two only mildly opposed
    readings is worth noting but not alarming (MILD_DIVERGENCE); two
    negligible opposite-sign readings isn't a meaningful conflict at all
    (still FULL_ALIGNMENT — the "divergence" would be noise, not signal).

    Returns None if either score is unavailable (mirrors every other
    scoring function in this codebase: no data in, no verdict out).
    """
    if spec_score is None or comm_score is None:
        return None

    if spec_score * comm_score >= 0:
        return AlignmentStatus.FULL_ALIGNMENT

    conflict_strength = (abs(spec_score) + abs(comm_score)) / 2.0
    if conflict_strength >= STRONG_DIVERGENCE_MIN:
        return AlignmentStatus.STRONG_DIVERGENCE
    if conflict_strength >= MILD_DIVERGENCE_MIN:
        return AlignmentStatus.MILD_DIVERGENCE
    return AlignmentStatus.FULL_ALIGNMENT


def apply_confidence_adjustment(confidence: float, status: Optional[AlignmentStatus]) -> float:
    """Apply the alignment-based confidence adjustment, clamped to 0-100. No-op if status is None."""
    if status is None:
        return confidence
    return max(0.0, min(100.0, confidence + CONFIDENCE_ADJUSTMENT_PCT[status]))


def describe_alignment(status: AlignmentStatus) -> dict:
    """
    Human-readable evidence/risk lines for a given alignment status, for
    agents/positioning_agent_base.py to fold into its AgentReport.
    Returns {"evidence": str, "risk": str | None, "catalyst": str | None}.
    """
    if status == AlignmentStatus.FULL_ALIGNMENT:
        return {
            "evidence": (
                "Institutional Alignment: commercial (long-term value) and speculative "
                "(current participation) positioning support the same direction, increasing conviction."
            ),
            "risk": None,
            "catalyst": "Commercial and speculative positioning are aligned, reinforcing this bias",
        }
    if status == AlignmentStatus.MILD_DIVERGENCE:
        return {
            "evidence": (
                "Institutional Divergence: long-term value (commercials) and current momentum "
                "(speculators) disagree moderately."
            ),
            "risk": (
                "Mild institutional divergence — require stronger technical confirmation before "
                "committing capital; this does not by itself invalidate the trade"
            ),
            "catalyst": None,
        }
    # STRONG_DIVERGENCE
    return {
        "evidence": (
            "High Institutional Uncertainty: commercial and speculative positioning are in strong "
            "divergence — structural value and current participation are conflicting significantly."
        ),
        "risk": (
            "Strong institutional divergence — increase caution, require exceptional technical "
            "confirmation and a higher reward-to-risk, and reduce preferred position size; absent "
            "strong confirmation, this favors No Trade"
        ),
        "catalyst": None,
    }


# --- Execution readiness (Chief Strategy Officer level) ---


class ExecutionReadiness(str, Enum):
    HIGH_CONVICTION = "high_conviction"
    CONDITIONAL_OPPORTUNITY = "conditional_opportunity"
    WATCHLIST = "watchlist"
    NO_TRADE = "no_trade"


EXECUTION_READINESS_BADGES = {
    ExecutionReadiness.HIGH_CONVICTION: "🟢",
    ExecutionReadiness.CONDITIONAL_OPPORTUNITY: "🟡",
    ExecutionReadiness.WATCHLIST: "🔵",
    ExecutionReadiness.NO_TRADE: "🔴",
}

EXECUTION_READINESS_LABELS = {
    ExecutionReadiness.HIGH_CONVICTION: "High Conviction Research Environment",
    ExecutionReadiness.CONDITIONAL_OPPORTUNITY: "Conditional Opportunity",
    ExecutionReadiness.WATCHLIST: "Watchlist",
    ExecutionReadiness.NO_TRADE: "No Trade",
}

# Confidence thresholds used by classify_execution_readiness. Named
# constants (not magic numbers) per this codebase's standing convention.
HIGH_CONVICTION_MIN_CONFIDENCE = 70.0
CONDITIONAL_MIN_CONFIDENCE = 50.0
NO_TRADE_MAX_CONFIDENCE = 30.0


def classify_execution_readiness(
    bias: Bias,
    confidence_score: float,
    risk_level: RiskLevel,
    technical_confirms: Optional[bool],
) -> ExecutionReadiness:
    """
    Per the spec: classify readiness rather than just bias direction.

    technical_confirms: True if a Chief Technical Officer report
    contributed to the synthesis AND its bias points the same direction as
    the overall bias; False if it contributed but disagrees; None if no
    technical department contributed this cycle (computed by
    ChiefStrategyOfficer.synthesize(), which is the only place that can
    see both the overall bias and each department's individual read).

    This is a deterministic decision table, not a scored/weighted formula
    — readiness is meant to be an easily-audited classification, matching
    how the spec describes it (four discrete tiers, not a continuum).
    """
    if bias == Bias.NEUTRAL or confidence_score <= NO_TRADE_MAX_CONFIDENCE:
        return ExecutionReadiness.NO_TRADE

    if risk_level == RiskLevel.HIGH:
        # High portfolio/positioning risk caps readiness at Conditional even
        # with otherwise-strong confidence — never High Conviction.
        return ExecutionReadiness.CONDITIONAL_OPPORTUNITY if confidence_score >= CONDITIONAL_MIN_CONFIDENCE else ExecutionReadiness.NO_TRADE

    if (
        confidence_score >= HIGH_CONVICTION_MIN_CONFIDENCE
        and risk_level in (RiskLevel.LOW, RiskLevel.MODERATE)
        and technical_confirms is True
    ):
        return ExecutionReadiness.HIGH_CONVICTION

    if confidence_score >= CONDITIONAL_MIN_CONFIDENCE:
        return ExecutionReadiness.CONDITIONAL_OPPORTUNITY

    return ExecutionReadiness.WATCHLIST


# --- Institutional commentary (deterministic, no LLM) ---

_ALIGNMENT_MARKERS = ("institutional alignment", "institutional divergence", "high institutional uncertainty")


def build_institutional_commentary(
    asset_or_theme: str,
    bias: Bias,
    confidence_score: float,
    execution_readiness: ExecutionReadiness,
    evidence: List[str],
    risks: List[str],
) -> str:
    """
    A short, deterministic paragraph explaining WHY, per the spec's
    "every report must explain WHY" requirement. Built entirely from
    template strings over already-computed values — no LLM call,
    consistent with every other narrative field in this platform (Chief
    Strategy Officer's trade_thesis/investment_committee_summary).

    Looks for an alignment-related line already emitted by a Chief
    Commodity/FX Analyst (see describe_alignment() above) among the
    aggregated evidence/risks and leads with it verbatim if present, since
    that's the most specific, on-topic explanation available; falls back
    to a generic bias/confidence framing when no positioning department
    contributed this cycle (e.g. a pure-equity or pure-macro synthesis).
    """
    institutional_line = None
    for line in evidence + risks:
        if any(marker in line.lower() for marker in _ALIGNMENT_MARKERS):
            institutional_line = line
            break

    if institutional_line:
        opening = institutional_line
    else:
        direction = bias.value.replace("_", " ")
        opening = f"{asset_or_theme} shows a {direction} bias at {confidence_score:.0f}/100 confidence."

    closing = {
        ExecutionReadiness.HIGH_CONVICTION: "Suitable for technical execution if the chart confirms.",
        ExecutionReadiness.CONDITIONAL_OPPORTUNITY: (
            "Fundamental bias is present, but technical confirmation is required before capital should be committed."
        ),
        ExecutionReadiness.WATCHLIST: "A directional edge may exist, but evidence remains incomplete — continue monitoring.",
        ExecutionReadiness.NO_TRADE: "Evidence is insufficient or risk is excessive; capital preservation is preferred.",
    }[execution_readiness]

    return f"{opening} {closing}"
