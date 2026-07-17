"""
Chief Equity Analyst.

Phase 4 scope: one agent instance per ticker/company (like the Phase 3
positioning agents are per-market), scoring a company's fundamental trend
from two SEC EDGAR XBRL series:

    - EarningsPerShareDiluted -> EPS trend
    - Revenues                -> revenue trend

Combined via the same 50/50 weighted-average pattern the Chief Macro
Officer (Phase 2) established, reusing agents.trend_scoring.series_trend_score
directly since SecEdgarConnector returns the same {"history": [{"value":...}]}
shape as FredConnector.

Per the full spec's equity coverage (buybacks, insider activity, valuation,
institutional ownership, market breadth, sector rotation...), those are the
natural next weighted components for a later phase — same agent, same
pattern, no architecture change.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .trend_scoring import series_trend_score

# Component weights (must sum to 100)
WEIGHT_EPS = 50
WEIGHT_REVENUE = 50


class ChiefEquityAnalyst(BaseAgent):
    department = "Chief Equity Analyst"

    def __init__(self, manager, eps_key: str, revenue_key: str, min_quality: float = 60.0):
        """
        eps_key / revenue_key: the keys this company's EPS and revenue
        SEC EDGAR datasets were registered under in the DataIntegrityManager,
        e.g. "SEC_AAPL_EPS", "SEC_AAPL_REVENUE".
        """
        super().__init__(manager, min_quality)
        self.eps_key = eps_key
        self.revenue_key = revenue_key

    def required_dataset_keys(self) -> List[str]:
        return [self.eps_key, self.revenue_key]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        catalysts: List[str] = []
        evidence: List[str] = []
        risks: List[str] = []
        component_scores: List[float] = []
        component_weights: List[float] = []

        eps_ds = usable.get(self.eps_key)
        if eps_ds is not None:
            eps_score = series_trend_score(eps_ds.payload.get("history", []), lower_is_bullish=False)
            if eps_score is not None:
                component_scores.append(eps_score)
                component_weights.append(WEIGHT_EPS)
                direction = "growing" if eps_score > 0 else "shrinking" if eps_score < 0 else "flat"
                evidence.append(
                    f"Diluted EPS is {direction} (latest={eps_ds.payload.get('latest_value')} "
                    f"as of {eps_ds.payload.get('latest_date')})"
                )
                if direction == "growing":
                    catalysts.append("Growing EPS supports a constructive earnings trajectory")
                elif direction == "shrinking":
                    risks.append("Shrinking EPS raises questions about earnings quality/trajectory")

        revenue_ds = usable.get(self.revenue_key)
        if revenue_ds is not None:
            revenue_score = series_trend_score(revenue_ds.payload.get("history", []), lower_is_bullish=False)
            if revenue_score is not None:
                component_scores.append(revenue_score)
                component_weights.append(WEIGHT_REVENUE)
                direction = "growing" if revenue_score > 0 else "shrinking" if revenue_score < 0 else "flat"
                evidence.append(
                    f"Revenue is {direction} (latest={revenue_ds.payload.get('latest_value')} "
                    f"as of {revenue_ds.payload.get('latest_date')})"
                )
                if direction == "growing":
                    catalysts.append("Top-line growth supports the fundamental thesis")
                elif direction == "shrinking":
                    risks.append("Contracting revenue is a headwind for the fundamental thesis")

        if component_scores:
            total_weight = sum(component_weights)
            bias_score = sum(s * w for s, w in zip(component_scores, component_weights)) / total_weight
        else:
            bias_score = 0.0

        confidence = 40.0 + (20.0 * len(component_scores))  # 40 base, +20 per usable component (max 80)
        risk_level = RiskLevel.MODERATE
        if len(usable) < len(self.required_dataset_keys()):
            risk_level = RiskLevel.ELEVATED
            confidence = max(0.0, confidence - 20.0)
        if not component_scores:
            risk_level = RiskLevel.HIGH
            confidence = 0.0

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=bias_from_score(bias_score),
            bias_score=round(bias_score, 1),
            confidence=round(confidence, 1),
            risk_level=risk_level,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=[],
        )
