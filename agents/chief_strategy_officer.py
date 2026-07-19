"""
Chief Strategy Officer.

Architecturally distinct from every prior agent: it is NOT a BaseAgent or a
PortfolioAgent, because it doesn't fetch any data through the
DataIntegrityManager at all. Its entire job is to consume AgentReports that
OTHER agents already produced (Chief Macro Officer, Chief Technical
Officer, etc.) and synthesize them — this is the layer where the platform's
"different departments can disagree with each other" design finally
matters, and where that disagreement gets resolved into one number rather
than left as nine side-by-side opinions.

Per the spec, this agent collects every department's report, weights the
evidence, resolves conflicts, and produces:
    - Overall Market Score (0-100)
    - Confidence Score (0-100)
    - Risk Level
    - Directional Bias
    - Trade Thesis
    - Catalysts / Risks
    - Invalidation levels
    - Investment Committee Summary

See docs/ARCHITECTURE_PHASE7.md for the weighting/disagreement math and
its rationale.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from models.report import AgentReport, Bias, RiskLevel, bias_from_score
from models.strategy_report import StrategyReport

from .risk_severity import worst_of

# Default per-department weights. Departments not listed default to 1.0.
# Sentiment/technical are weighted a bit below the fundamental desks by
# default (configurable per instance) — a common institutional convention
# of treating fundamentals as the primary driver and technicals/sentiment
# as confirming/timing signals, not the other way around.
DEFAULT_DEPARTMENT_WEIGHTS: Dict[str, float] = {
    "Chief Sentiment Officer": 0.7,
    "Chief Technical Officer": 0.7,
}

RISK_OFFICER_DEPARTMENT = "Chief Risk Officer"

# Disagreement penalty: a weighted stdev of 100 (bias scores maximally
# spread from -100 to +100 with balanced weight) caps the confidence
# penalty at 40 points. A stdev of 25 (mild disagreement) costs only 10.
DISAGREEMENT_PENALTY_SCALE = 0.4
DISAGREEMENT_PENALTY_CAP = 40.0


def _weighted_mean(values: List[float], weights: List[float]) -> float:
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def _weighted_stdev(values: List[float], weights: List[float]) -> float:
    total_weight = sum(weights)
    if total_weight == 0 or len(values) < 2:
        return 0.0
    mean = _weighted_mean(values, weights)
    variance = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total_weight
    return variance ** 0.5


class ChiefStrategyOfficer:
    department = "Chief Strategy Officer"

    def __init__(self, department_weights: Optional[Dict[str, float]] = None):
        self.department_weights = {**DEFAULT_DEPARTMENT_WEIGHTS, **(department_weights or {})}

    def _weight_for(self, department: str) -> float:
        return self.department_weights.get(department, 1.0)

    def synthesize(
        self,
        asset_or_theme: str,
        reports: List[AgentReport],
        risk_report: Optional[AgentReport] = None,
    ) -> StrategyReport:
        """
        reports: AgentReports from directional departments (Macro, Bond,
            Commodity, FX, Equity, Crypto, Sentiment, Technical) for the
            SAME asset_or_theme.
        risk_report: optionally, the Chief Risk Officer's portfolio-level
            report. It is deliberately EXCLUDED from the bias_score
            weighting (its bias is always neutral/0 by design — see
            docs/ARCHITECTURE_PHASE6.md — including it would incorrectly
            drag the directional synthesis toward neutral) but its
            risk_level and risks/catalysts DO feed into the final output,
            since portfolio-level risk is exactly the kind of thing a real
            investment committee needs to hear regardless of direction.
        """
        contributing: List[str] = []
        excluded: List[str] = []
        bias_scores: List[float] = []
        weights: List[float] = []
        confidences: List[float] = []
        all_catalysts: List[str] = []
        all_risks: List[str] = []
        risk_levels: List[RiskLevel] = []

        for report in reports:
            effective_weight = self._weight_for(report.department) * (report.confidence / 100.0)
            if effective_weight > 0:
                contributing.append(report.department)
                bias_scores.append(report.bias_score)
                weights.append(effective_weight)
                confidences.append(report.confidence)
                risk_levels.append(report.risk_level)
            else:
                excluded.append(report.department)
            all_catalysts.extend(report.catalysts)
            all_risks.extend(report.risks)

        if risk_report is not None:
            risk_levels.append(risk_report.risk_level)
            all_catalysts.extend(risk_report.catalysts)
            all_risks.extend(risk_report.risks)

        # --- Directional synthesis (Risk Officer excluded, see docstring) ---
        if bias_scores:
            overall_bias_score = _weighted_mean(bias_scores, weights)
            disagreement = _weighted_stdev(bias_scores, weights)
            avg_confidence = _weighted_mean(confidences, weights)
            penalty = min(DISAGREEMENT_PENALTY_CAP, disagreement * DISAGREEMENT_PENALTY_SCALE)
            confidence_score = max(0.0, avg_confidence - penalty)
        else:
            overall_bias_score = 0.0
            disagreement = 0.0
            confidence_score = 0.0

        overall_market_score = (overall_bias_score + 100.0) / 2.0  # map -100..100 -> 0..100
        bias = bias_from_score(overall_bias_score)
        risk_level = worst_of(risk_levels) if risk_levels else RiskLevel.MODERATE

        # --- Aggregate catalysts/risks (dedupe, preserve first-seen order, cap length) ---
        catalysts = list(dict.fromkeys(all_catalysts))[:8]
        risks = list(dict.fromkeys(all_risks))[:8]

        # --- Invalidation notes (qualitative — see docs/ARCHITECTURE_PHASE7.md
        # for why this isn't a hard price level yet) ---
        invalidation_notes = [f"Thesis is weakened if: {r}" for r in risks[:3]]

        trade_thesis = self._build_trade_thesis(
            asset_or_theme, bias, overall_bias_score, confidence_score,
            len(contributing), len(reports), disagreement,
        )
        investment_committee_summary = self._build_committee_summary(
            asset_or_theme, bias, overall_market_score, confidence_score, risk_level,
            contributing, excluded, catalysts, risks,
        )

        return StrategyReport(
            asset_or_theme=asset_or_theme,
            overall_market_score=round(overall_market_score, 1),
            confidence_score=round(confidence_score, 1),
            risk_level=risk_level,
            bias=bias,
            bias_score=round(overall_bias_score, 1),
            trade_thesis=trade_thesis,
            investment_committee_summary=investment_committee_summary,
            catalysts=catalysts,
            risks=risks,
            invalidation_notes=invalidation_notes,
            contributing_departments=contributing,
            excluded_departments=excluded,
        )

    def _build_trade_thesis(
        self, asset_or_theme, bias, bias_score, confidence_score, n_contributing, n_total, disagreement,
    ) -> str:
        if n_contributing == 0:
            return (
                f"{asset_or_theme}: no department produced usable data for this cycle — "
                f"no thesis can be formed."
            )

        agreement_note = (
            "departments are broadly aligned" if disagreement < 25
            else "departments show meaningful disagreement" if disagreement < 60
            else "departments are sharply divided"
        )
        return (
            f"{asset_or_theme}: {bias.value.replace('_', ' ')} bias (score {bias_score:+.1f}/100) "
            f"with {confidence_score:.0f}/100 confidence, synthesized across {n_contributing} of "
            f"{n_total} departments — {agreement_note}."
        )

    def _build_committee_summary(
        self, asset_or_theme, bias, overall_market_score, confidence_score, risk_level,
        contributing, excluded, catalysts, risks,
    ) -> str:
        parts = [
            f"{asset_or_theme} — Overall Market Score {overall_market_score:.0f}/100, "
            f"Confidence {confidence_score:.0f}/100, Risk Level {risk_level.value.upper()}.",
            f"Directional bias: {bias.value.replace('_', ' ')}.",
        ]
        if contributing:
            parts.append(f"Contributing departments: {', '.join(contributing)}.")
        if excluded:
            parts.append(f"Excluded (no usable data this cycle): {', '.join(excluded)}.")
        if catalysts:
            parts.append("Key catalysts: " + "; ".join(catalysts[:3]) + ".")
        if risks:
            parts.append("Key risks: " + "; ".join(risks[:3]) + ".")
        return " ".join(parts)
