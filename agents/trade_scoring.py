"""
Scoring helpers for agents/chief_trade_decision_officer.py.

Kept as pure functions (no state, no I/O) in their own module — same
pattern as agents/positioning_scoring.py and agents/risk_calculations.py —
so every number the Trade Decision Engine produces can be tested in
isolation and explained by pointing at one small function, not traced
through the whole orchestrating agent.

Core principle enforced by construction (spec section 1): fundamental_score,
technical_score, and risk_score are computed independently, from disjoint
sets of AgentReports. Nothing in this module ever derives one of the three
from another, and overall_score is only ever a documented weighted blend
of all three, never a stand-in for any single one.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from models.report import AgentReport, RiskLevel
from models.trade_decision import EntryConfirmation, ExecutionRating, TradeGrade

# Departments whose bias_score feeds the Fundamental Score (macro/COT/
# positioning desks). Chief Technical Officer is deliberately excluded —
# it is the entire Technical Score, not a fundamental input, per spec
# section 1's explicit split between the two categories.
FUNDAMENTAL_DEPARTMENTS = {
    "Chief Macro Officer",
    "Chief Bond Strategist",
    "Chief Commodity Analyst",
    "Chief FX Analyst",
    "Chief Equity Analyst",
    "Chief Cryptocurrency Analyst",
    "Chief Sentiment Officer",
}

TECHNICAL_DEPARTMENT = "Chief Technical Officer"

RISK_DEPARTMENTS = {"Chief Risk Officer", "Chief Asset Risk Officer"}

WEIGHT_FUNDAMENTAL = 0.40
WEIGHT_TECHNICAL = 0.40
WEIGHT_RISK = 0.20

RISK_LEVEL_BASE_SCORE = {
    RiskLevel.LOW: 90.0,
    RiskLevel.MODERATE: 70.0,
    RiskLevel.ELEVATED: 45.0,
    RiskLevel.HIGH: 20.0,
}
# Each additional distinct flagged risk (beyond whatever already set the
# risk_level) shaves a further 5 points off the Risk Score, floor 0 —
# risk_level already captures the worst single factor; this lets several
# simultaneous smaller risk flags (e.g. both an ATR expansion AND a
# weekend gap) still be reflected rather than swallowed by one flag.
PER_EXTRA_RISK_PENALTY = 5.0

MIN_BIAS_MAGNITUDE_FOR_DIRECTION = 15.0  # matches models/report.py's bias_from_score neutral band


def _bias_score_to_100(bias_score: float) -> float:
    """Map a -100..+100 bias_score onto a 0..100 score scale."""
    return max(0.0, min(100.0, (bias_score + 100.0) / 2.0))


def fundamental_score(reports: List[AgentReport]) -> Tuple[float, List[str], List[str]]:
    """
    Confidence-weighted mean of every fundamental department's bias_score,
    mapped to 0-100. Returns (score, contributing_departments, excluded_departments).
    A department with confidence 0 contributes zero weight (same
    "confidence gates influence" convention as
    agents/chief_strategy_officer.py's _weighted_mean).
    """
    contributing, excluded = [], []
    scores, weights = [], []

    for r in reports:
        if r.department not in FUNDAMENTAL_DEPARTMENTS:
            continue
        w = r.confidence / 100.0
        if w > 0:
            contributing.append(r.department)
            scores.append(_bias_score_to_100(r.bias_score))
            weights.append(w)
        else:
            excluded.append(r.department)

    if not scores:
        return 50.0, contributing, excluded  # neutral midpoint if nothing usable

    total_weight = sum(weights)
    score = sum(s * w for s, w in zip(scores, weights)) / total_weight
    return round(score, 1), contributing, excluded


def technical_score(technical_report: Optional[AgentReport]) -> Tuple[float, List[str], List[str]]:
    """Chief Technical Officer's bias_score, mapped to 0-100."""
    if technical_report is None:
        return 50.0, [], [TECHNICAL_DEPARTMENT]
    if technical_report.confidence <= 0:
        return 50.0, [], [TECHNICAL_DEPARTMENT]
    return round(_bias_score_to_100(technical_report.bias_score), 1), [TECHNICAL_DEPARTMENT], []


def risk_score(risk_reports: List[AgentReport]) -> Tuple[float, List[str], List[str]]:
    """
    Worst-case risk_level across all risk desks sets the base score;
    every distinct flagged risk beyond the first shaves off additional
    points (floor 0). Higher score = LOWER risk, per spec section 1.
    """
    contributing = [r.department for r in risk_reports if r.department in RISK_DEPARTMENTS]
    excluded = [d for d in RISK_DEPARTMENTS if d not in contributing]

    relevant = [r for r in risk_reports if r.department in RISK_DEPARTMENTS]
    if not relevant:
        return 50.0, contributing, excluded  # neutral if no risk desk ran

    worst_level = RiskLevel.LOW
    all_risks: List[str] = []
    for r in relevant:
        if RISK_LEVEL_BASE_SCORE[r.risk_level] < RISK_LEVEL_BASE_SCORE[worst_level]:
            worst_level = r.risk_level
        all_risks.extend(r.risks)

    distinct_risks = list(dict.fromkeys(all_risks))
    base = RISK_LEVEL_BASE_SCORE[worst_level]
    penalty = max(0, len(distinct_risks) - 1) * PER_EXTRA_RISK_PENALTY
    score = max(0.0, base - penalty)
    return round(score, 1), contributing, excluded


def overall_score(fundamental: float, technical: float, risk: float) -> float:
    return round(
        fundamental * WEIGHT_FUNDAMENTAL + technical * WEIGHT_TECHNICAL + risk * WEIGHT_RISK, 1,
    )


def build_entry_confirmation(
    technical_report: Optional[AgentReport],
    fundamental_score_value: float,
    risk_score_value: float,
    min_risk_score: float = 45.0,
    min_fundamental_alignment: float = 55.0,
) -> EntryConfirmation:
    """
    Section 8: every requirement checked individually. Built from what the
    existing AgentReports actually contain today — evidence/catalysts
    strings that mention specific technical concepts — rather than
    inventing new required datasets this phase doesn't have yet
    (documented simplification, same "don't hide it" convention used
    throughout this platform; a later phase can wire in explicit
    order-block/FVG/volume-profile detectors and replace the string checks
    below with real structural checks).
    """
    ec = EntryConfirmation()

    if technical_report is None or technical_report.confidence <= 0:
        ec.notes.append("No usable technical report — trend/structure/breakout/volume cannot be confirmed")
        ec.risk_acceptable = risk_score_value >= min_risk_score
        if not ec.risk_acceptable:
            ec.notes.append(f"Risk Score ({risk_score_value:.0f}) is below the {min_risk_score:.0f} minimum")
        ec.macro_alignment = fundamental_score_value >= min_fundamental_alignment or fundamental_score_value <= (100 - min_fundamental_alignment)
        return ec

    evidence_blob = " ".join(technical_report.evidence).lower()
    catalysts_blob = " ".join(technical_report.catalysts).lower()

    ec.trend_alignment = "uptrend" in evidence_blob or "downtrend" in evidence_blob
    if not ec.trend_alignment:
        ec.notes.append("No clear trend detected (20/50 SMA structure is flat)")

    # Market structure / breakout / volume: this phase's Technical Officer
    # doesn't yet compute BOS/CHoCH or a volume series (see module
    # docstring) — treated as confirmed only when the MACD histogram
    # agrees with the SMA trend direction, a reasonable proxy for
    # "momentum confirming structure" until those detectors exist.
    macd_up = "accelerating higher" in evidence_blob
    macd_down = "accelerating lower" in evidence_blob
    trend_up = "an uptrend" in evidence_blob or "uptrend" in catalysts_blob
    trend_down = "a downtrend" in evidence_blob or "downtrend" in catalysts_blob
    structure_confirmed = (macd_up and trend_up) or (macd_down and trend_down)
    ec.market_structure_confirmed = structure_confirmed
    ec.breakout_confirmed = structure_confirmed
    ec.volume_confirmed = structure_confirmed
    if not structure_confirmed:
        ec.notes.append("Momentum (MACD) does not yet confirm the structural trend direction")

    ec.liquidity_confirmed = technical_report.risk_level != RiskLevel.HIGH
    if not ec.liquidity_confirmed:
        ec.notes.append("Technical risk level is HIGH — liquidity/volatility conditions not confirmed")

    ec.macro_alignment = fundamental_score_value >= min_fundamental_alignment or fundamental_score_value <= (100 - min_fundamental_alignment)
    if not ec.macro_alignment:
        ec.notes.append(f"Fundamental Score ({fundamental_score_value:.0f}) is too close to neutral to align with a directional entry")

    ec.risk_acceptable = risk_score_value >= min_risk_score
    if not ec.risk_acceptable:
        ec.notes.append(f"Risk Score ({risk_score_value:.0f}) is below the {min_risk_score:.0f} minimum")

    # Minimum RR: no stop/target inputs exist yet in this phase — treated
    # as satisfied only when risk is acceptable AND both other legs agree,
    # documented the same way as the structure proxy above.
    ec.minimum_rr_achieved = ec.risk_acceptable and ec.market_structure_confirmed and ec.macro_alignment
    if not ec.minimum_rr_achieved and ec.risk_acceptable and ec.macro_alignment:
        ec.notes.append("Minimum risk/reward not yet achieved — awaiting structural confirmation")

    return ec


def execution_rating(
    fundamental_score_value: float, technical_score_value: float, risk_score_value: float,
    entry_confirmation: EntryConfirmation,
) -> ExecutionRating:
    """
    Section 5. Never derived from overall_score directly — always from the
    individual legs plus the entry-confirmation checklist, so a strong
    Overall Score built on a weak/failing checklist can never read as
    ENTER NOW (the exact failure mode spec section 1 forbids).
    """
    has_directional_bias = (
        abs(fundamental_score_value - 50.0) >= MIN_BIAS_MAGNITUDE_FOR_DIRECTION / 2
        or abs(technical_score_value - 50.0) >= MIN_BIAS_MAGNITUDE_FOR_DIRECTION / 2
    )

    if not has_directional_bias:
        return ExecutionRating.AVOID

    if risk_score_value < 30.0:
        return ExecutionRating.AVOID

    if entry_confirmation.all_passed() and risk_score_value >= 45.0:
        return ExecutionRating.ENTER_NOW

    technical_partially_confirmed = entry_confirmation.trend_alignment or entry_confirmation.market_structure_confirmed
    if technical_partially_confirmed and risk_score_value >= 40.0:
        return ExecutionRating.WAIT_FOR_CONFIRMATION

    if risk_score_value >= 30.0:
        return ExecutionRating.WATCHLIST

    return ExecutionRating.AVOID


def trade_grade(
    overall_score_value: float, fundamental_score_value: float,
    technical_score_value: float, risk_score_value: float,
) -> TradeGrade:
    """
    Section 6. Deliberately requires balance, not just a high average — an
    Overall Score of 80 built on a Risk Score of 20 should never grade as
    A-tier, so the worst of the three legs caps the grade regardless of
    the blended overall_score.
    """
    weakest_leg = min(fundamental_score_value, technical_score_value, risk_score_value)

    if overall_score_value >= 85 and weakest_leg >= 70:
        return TradeGrade.A_PLUS
    if overall_score_value >= 75 and weakest_leg >= 60:
        return TradeGrade.A
    if overall_score_value >= 68 and weakest_leg >= 50:
        return TradeGrade.A_MINUS
    if overall_score_value >= 60 and weakest_leg >= 40:
        return TradeGrade.B_PLUS
    if overall_score_value >= 52 and weakest_leg >= 30:
        return TradeGrade.B
    if overall_score_value >= 45 and weakest_leg >= 25:
        return TradeGrade.B_MINUS
    if overall_score_value >= 35:
        return TradeGrade.C
    return TradeGrade.D
