"""
Chief Strategy Officer.

Architecturally distinct from every prior agent: it is NOT a BaseAgent or a
PortfolioAgent, because it doesn't fetch any data through the
DataIntegrityManager at all. Its entire job is to consume AgentReports that
OTHER agents already produced (Chief Macro Officer, Chief Sentiment
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

from datetime import date
from typing import Dict, List, Optional, Set

from models.report import AgentReport, Bias, RiskLevel, bias_from_score
from models.strategy_report import StrategyReport

from .risk_severity import worst_of
from .institutional_relationship import classify_execution_readiness, build_institutional_commentary, ExecutionReadiness
from .weighted_stats import weighted_mean as _weighted_mean, weighted_stdev as _weighted_stdev
from .market_regime import classify_regime, regime_adjusted_weight, MarketRegime
from config.fomc_meeting_dates import FOMC_MEETING_DATES

# Maps a department name to the category name agents.market_regime.py's
# REGIME_CATEGORY_MULTIPLIERS uses — only departments with a genuine,
# unambiguous category match are included here; anything not listed
# simply gets no regime adjustment (base weight only), rather than
# guessing a category for a department the regime module was never
# scoped to cover.
DEPARTMENT_TO_REGIME_CATEGORY: Dict[str, str] = {
    "Chief Macro Officer": "Macroeconomic",
    "Chief Equity Analyst": "Equity Fundamentals",
}

# Default per-department weights. Departments not listed default to 1.0.
# Sentiment is weighted a bit below the fundamental desks by default
# (configurable per instance) — a common institutional convention of
# treating fundamentals as the primary driver and sentiment as a
# confirming/timing signal, not the other way around. (Chief Technical
# Officer used to have an entry here too; that department was removed
# from the platform's main scoring pipeline entirely per user request —
# see docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md.)
# Default per-department weights. Departments not listed default to 1.0.
#
# Sentiment is weighted a bit below the fundamental desks by default — a
# common institutional convention of treating fundamentals as the primary
# driver and sentiment as a confirming/timing signal, not the other way
# around.
#
# Chief Commodity Analyst / Chief FX Analyst are weighted SIGNIFICANTLY
# below the fundamental desks (Macro, Bond, Equity, Crypto all stay at the
# 1.0 default) per an explicit later decision: COT (Non-Commercial
# speculative positioning) is now used only as a supporting confirmation
# signal, never as the primary reason for a trade — see
# docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md. This is on top of (not
# instead of) that decision's other change: Commercial Traders were removed
# from those departments' own bias/confidence scoring entirely.
DEFAULT_DEPARTMENT_WEIGHTS: Dict[str, float] = {
    "Chief Sentiment Officer": 0.7,
    "Chief Commodity Analyst": 0.4,
    "Chief FX Analyst": 0.4,
    # Seasonality is explicitly a supporting/minor signal per the spec's
    # own Final Investment Committee weighting — a documented historical
    # pattern (see agents/seasonality_scoring.py's honest-scope docstring),
    # not live-measured data, so it gets the lowest default weight of any
    # department: even lower than COT, which is at least based on live
    # positioning data rather than a widely-cited calendar heuristic.
    "Chief Seasonality Officer": 0.3,
}

RISK_OFFICER_DEPARTMENT = "Chief Risk Officer"

# Disagreement penalty: a weighted stdev of 100 (bias scores maximally
# spread from -100 to +100 with balanced weight) caps the confidence
# penalty at 40 points. A stdev of 25 (mild disagreement) costs only 10.
DISAGREEMENT_PENALTY_SCALE = 0.4
DISAGREEMENT_PENALTY_CAP = 40.0


class ChiefStrategyOfficer:
    department = "Chief Strategy Officer"

    def __init__(self, department_weights: Optional[Dict[str, float]] = None):
        self.department_weights = {**DEFAULT_DEPARTMENT_WEIGHTS, **(department_weights or {})}

    def _weight_for(self, department: str, active_regimes: Optional[Set[MarketRegime]] = None) -> float:
        base = self.department_weights.get(department, 1.0)
        if not active_regimes:
            return base
        category = DEPARTMENT_TO_REGIME_CATEGORY.get(department)
        if category is None:
            return base
        return regime_adjusted_weight(base, category, active_regimes)

    def synthesize(
        self,
        asset_or_theme: str,
        reports: List[AgentReport],
        risk_report: Optional[AgentReport] = None,
        risk_reports: Optional[List[AgentReport]] = None,
        reference_date: Optional[date] = None,
    ) -> StrategyReport:
        """
        reports: AgentReports from directional departments (Macro, Bond,
            Commodity, FX, Equity, Crypto, Sentiment, Seasonality) for the
            SAME asset_or_theme. (Chief Technical Officer used to be
            included here too; it was removed from the platform's main
            scoring pipeline per user request — see
            docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md.)
        risk_report: optionally, the Chief Risk Officer's portfolio-level
            report. It is deliberately EXCLUDED from the bias_score
            weighting (its bias is always neutral/0 by design — see
            docs/ARCHITECTURE_PHASE6.md — including it would incorrectly
            drag the directional synthesis toward neutral) but its
            risk_level and risks/catalysts DO feed into the final output,
            since portfolio-level risk is exactly the kind of thing a real
            investment committee needs to hear regardless of direction.
        risk_reports: optionally, any number of OTHER risk-type reports
            that should be treated the same way as risk_report (bias
            excluded, risk_level/risks/catalysts included) — e.g.
            agents.chief_risk_fundamentals_officer.ChiefRiskFundamentalsOfficer's
            per-asset volatility/drawdown read. "Low volatility" is a
            claim about stability, not a claim that the asset will rise —
            folding it into the directional bias average the same way a
            Macro or Sentiment reading is would misrepresent what the
            signal actually means, so it gets the same treatment as the
            portfolio Risk Officer instead.
        reference_date: defaults to today. Used to classify the active
            market regime (agents.market_regime.classify_regime) ONCE for
            this whole synthesis call, then applied as a dynamic
            multiplier on top of each department's static default weight
            for the departments agents.market_regime.py actually covers
            (Chief Macro Officer during an FOMC week, Chief Equity Analyst
            during earnings season) — see
            docs/ARCHITECTURE_DYNAMIC_REGIME_WEIGHTING.md. Every other
            department's weight is completely unaffected. Pass an
            explicit date for deterministic testing.
        """
        active_regimes = classify_regime(reference_date or date.today(), FOMC_MEETING_DATES)

        # Defensive deduplication by department name — found via live
        # testing that a caller (the Department Reports dashboard page)
        # could pass the same department's report twice (e.g. after
        # re-running it), which would silently DOUBLE-WEIGHT that
        # department in the blend below with no defense against it. Fixed
        # at the dashboard source too, but kept here as well so this core
        # synthesis logic is correct regardless of what any current or
        # future caller passes in — never trusting the caller to have
        # already deduplicated. Keeps the LAST occurrence of each
        # department (the most recently produced report), consistent
        # with "the newest run replaces the previous one" being the
        # expected behavior everywhere else in this platform.
        deduped_reports: Dict[str, AgentReport] = {}
        for report in reports:
            deduped_reports[report.department] = report
        reports = list(deduped_reports.values())

        contributing: List[str] = []
        excluded: List[str] = []
        bias_scores: List[float] = []
        weights: List[float] = []
        confidences: List[float] = []
        all_catalysts: List[str] = []
        all_risks: List[str] = []
        all_evidence: List[str] = []
        risk_levels: List[RiskLevel] = []
        contributing_weighted: List[tuple] = []  # (department, bias_score, effective_weight, confidence) for contributing departments only — feeds _build_decision_explanation and the committee table

        for report in reports:
            effective_weight = self._weight_for(report.department, active_regimes) * (report.confidence / 100.0)
            if effective_weight > 0:
                contributing.append(report.department)
                bias_scores.append(report.bias_score)
                weights.append(effective_weight)
                confidences.append(report.confidence)
                risk_levels.append(report.risk_level)
                contributing_weighted.append((report.department, report.bias_score, effective_weight, report.confidence))
            else:
                excluded.append(report.department)
            all_catalysts.extend(report.catalysts)
            all_risks.extend(report.risks)
            all_evidence.extend(report.evidence)

        if risk_report is not None:
            risk_levels.append(risk_report.risk_level)
            all_catalysts.extend(risk_report.catalysts)
            all_risks.extend(risk_report.risks)

        # Same defensive deduplication as the directional `reports` above
        # — a duplicated risk_report wouldn't distort the bias average
        # (risk reports are already excluded from that), but it WOULD
        # cause the same risks/catalysts text to appear twice in the
        # final output.
        deduped_risk_reports: Dict[str, AgentReport] = {}
        for extra_risk_report in (risk_reports or []):
            deduped_risk_reports[extra_risk_report.department] = extra_risk_report

        for extra_risk_report in deduped_risk_reports.values():
            risk_levels.append(extra_risk_report.risk_level)
            all_catalysts.extend(extra_risk_report.catalysts)
            all_risks.extend(extra_risk_report.risks)

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

        # --- Execution readiness & institutional commentary ---
        # Execution readiness used to also depend on whether a Chief
        # Technical Officer report confirmed the overall bias. That
        # department was removed from the platform's main scoring pipeline
        # entirely (per user request — the platform now scores purely on
        # fundamentals, macro, and global news/sentiment), so readiness is
        # judged on confidence and risk alone now. See
        # docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md.
        execution_readiness = classify_execution_readiness(bias, confidence_score, risk_level)
        institutional_commentary = build_institutional_commentary(
            asset_or_theme, bias, confidence_score, execution_readiness, evidence=all_evidence, risks=risks,
        )
        decision_explanation = self._build_decision_explanation(
            asset_or_theme, bias, overall_bias_score, contributing_weighted, risks, invalidation_notes,
        )
        committee_table = self._build_committee_table(contributing_weighted)
        committee_recommendation = self._build_committee_recommendation(bias, execution_readiness)

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
            execution_readiness=execution_readiness.value,
            institutional_commentary=institutional_commentary,
            decision_explanation=decision_explanation,
            committee_table=committee_table,
            committee_recommendation=committee_recommendation,
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

    def _build_decision_explanation(
        self, asset_or_theme, bias, overall_bias_score, contributing_weighted, risks, invalidation_notes,
    ) -> str:
        """
        Per the spec's "Explain Every Decision" requirement: after
        generating the final bias, produce a detailed explanation showing
        why each factor is bullish/bearish/neutral, which had the greatest
        influence, which conflicted with the final decision, the
        strongest risks, and what could invalidate the analysis. Built
        entirely from already-computed values via template strings — no
        LLM call, consistent with every other narrative field in this
        platform (trade_thesis, investment_committee_summary,
        institutional_commentary).

        contributing_weighted: list of (department, bias_score,
        effective_weight, confidence) tuples for departments that
        actually contributed — the exact same data already used to
        compute the overall bias, so "greatest influence" and
        "conflicting" are derived from the real weighting, not re-guessed.
        """
        if not contributing_weighted:
            return (
                f"{asset_or_theme}: no department contributed usable data this cycle — "
                f"no decision explanation can be formed."
            )

        # 1. Why each factor is bullish/bearish/neutral
        factor_lines = []
        for department, dept_bias_score, _weight, _confidence in contributing_weighted:
            label = "bullish" if dept_bias_score > 15 else "bearish" if dept_bias_score < -15 else "neutral"
            factor_lines.append(f"{department} is {label} (score {dept_bias_score:+.1f})")
        parts = ["Department reads: " + "; ".join(factor_lines) + "."]

        # 2. Which factors had the greatest influence — ranked by the
        # SAME effective_weight (department weight * confidence/100)
        # actually used to compute the overall bias.
        ranked = sorted(contributing_weighted, key=lambda t: t[2], reverse=True)
        top = ranked[:2]
        if top:
            top_desc = ", ".join(f"{d} (effective weight {w:.2f})" for d, _s, w, _c in top)
            parts.append(f"Greatest influence on this synthesis: {top_desc}.")

        # 3. Which factors conflicted with the final decision — opposite
        # sign to the overall bias, both meaningfully non-neutral (>15,
        # matching bias_from_score's own neutral-band convention).
        conflicting = [
            d for d, s, _w, _c in contributing_weighted
            if abs(s) > 15 and abs(overall_bias_score) > 15 and (s > 0) != (overall_bias_score > 0)
        ]
        if conflicting:
            parts.append(
                f"Departments conflicting with the final {bias.value.replace('_', ' ')} bias: "
                f"{', '.join(conflicting)}."
            )
        else:
            parts.append("No department meaningfully conflicts with the final bias.")

        # 4. Strongest risks (already deduped/capped upstream)
        if risks:
            parts.append("Strongest risks: " + "; ".join(risks[:3]) + ".")

        # 5. What could invalidate the analysis
        if invalidation_notes:
            cleaned = [n.replace("Thesis is weakened if: ", "") for n in invalidation_notes]
            parts.append("This thesis could be invalidated if: " + "; ".join(cleaned) + ".")

        return " ".join(parts)

    def _build_committee_table(self, contributing_weighted) -> List[dict]:
        """
        Per the spec's exact "Final Investment Committee" table format:
        Factor | Bias | Weight | Confidence. Weight is normalized to a
        percentage of the TOTAL effective weight across contributing
        departments, so the column sums to 100% — matching the spec's own
        example table (30% + 25% + 15% + 10% + 10% + 10% = 100%), and
        computed from the exact same effective_weight already used to
        calculate the overall bias, not re-derived separately.

        Returns an empty list if nothing contributed — never a fabricated
        row for a department that produced no usable data this cycle.
        """
        if not contributing_weighted:
            return []
        total_weight = sum(w for _d, _s, w, _c in contributing_weighted)
        if total_weight == 0:
            return []

        rows = [
            {
                "department": department,
                "bias": bias_from_score(dept_bias_score).value,
                "weight_pct": round((weight / total_weight) * 100, 1),
                "confidence": round(confidence, 1),
            }
            for department, dept_bias_score, weight, confidence in contributing_weighted
        ]
        # Most influential department first, matching how a real
        # investment committee summary presents its inputs.
        rows.sort(key=lambda r: r["weight_pct"], reverse=True)
        return rows

    def _build_committee_recommendation(self, bias: Bias, execution_readiness: "ExecutionReadiness") -> str:
        """
        A plain research-stance label, matching the spec's "Investment
        Committee Recommendation: Long" format. Explicitly phrased as a
        "research view," never a bare instruction like "Long" or "Buy" —
        this platform never places trades or issues execution commands
        (see every architecture doc since Phase 1); this is a research
        conclusion label, not a trade instruction.
        """
        if execution_readiness == ExecutionReadiness.NO_TRADE or bias == Bias.NEUTRAL:
            return "Hold / No Trade (research view)"
        if bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH):
            return "Long (research view)"
        return "Short (research view)"
