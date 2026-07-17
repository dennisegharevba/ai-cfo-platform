"""
Chief Macro Officer.

Scope for Phase 2 (per the spec's macro coverage list, starting with the two
most load-bearing series — more FRED series slot in as later phases extend
this agent, same pattern, no architecture change needed):

    - CPIAUCSL (CPI, all urban consumers) -> inflation trend
    - UNRATE   (Unemployment rate)         -> labor market trend

Produces a single "Growth & Inflation Regime" bias on risk assets in general:
inflation decelerating + unemployment falling => bullish regime for risk
assets; inflation accelerating + unemployment rising => bearish regime.

Scoring is a simple, auditable weighted average of two trend components,
each in -100..+100, so any conclusion can be explained in one sentence
without needing to inspect model internals.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, Bias, RiskLevel, bias_from_score

from .base_agent import BaseAgent

# Registration keys this agent expects to find in the DataIntegrityManager
KEY_CPI = "FRED_CPI"
KEY_UNRATE = "FRED_UNRATE"

# Component weights (must sum to 100)
WEIGHT_INFLATION = 50
WEIGHT_LABOR = 50


def _series_trend_score(history: List[dict], lower_is_bullish: bool) -> Optional[float]:
    """
    Compare the latest observation to the earliest available one in the
    supplied history window and produce a -100..+100 trend score.

    lower_is_bullish=True means a falling series (e.g. unemployment,
    decelerating inflation) is the bullish direction for this component.

    Returns None if there isn't enough history to compute a trend.
    """
    values = []
    for obs in history:
        raw = obs.get("value")
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue

    if len(values) < 2:
        return None

    latest = values[0]   # FRED connector returns observations sorted desc (newest first)
    earliest = values[-1]

    if earliest == 0:
        return None

    pct_change = (latest - earliest) / abs(earliest) * 100
    # Normalize: a swing of +/-5% over the window is treated as a strong move.
    normalized = max(-100.0, min(100.0, (pct_change / 5.0) * 100))

    return -normalized if lower_is_bullish else normalized


class ChiefMacroOfficer(BaseAgent):
    department = "Chief Macro Officer"

    def required_dataset_keys(self) -> List[str]:
        return [KEY_CPI, KEY_UNRATE]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        catalysts: List[str] = []
        evidence: List[str] = []
        risks: List[str] = []
        component_scores: List[float] = []
        component_weights: List[float] = []

        cpi_ds = usable.get(KEY_CPI)
        if cpi_ds is not None:
            cpi_score = _series_trend_score(cpi_ds.payload.get("history", []), lower_is_bullish=True)
            if cpi_score is not None:
                component_scores.append(cpi_score)
                component_weights.append(WEIGHT_INFLATION)
                direction = "decelerating" if cpi_score > 0 else "accelerating" if cpi_score < 0 else "flat"
                evidence.append(
                    f"CPI is {direction} (latest={cpi_ds.payload.get('latest_value')} "
                    f"as of {cpi_ds.payload.get('latest_date')})"
                )
                if direction == "accelerating":
                    risks.append("Re-accelerating inflation could force a more hawkish policy path")
                elif direction == "decelerating":
                    catalysts.append("Disinflation trend supports continued policy easing expectations")

        unrate_ds = usable.get(KEY_UNRATE)
        if unrate_ds is not None:
            labor_score = _series_trend_score(unrate_ds.payload.get("history", []), lower_is_bullish=True)
            if labor_score is not None:
                component_scores.append(labor_score)
                component_weights.append(WEIGHT_LABOR)
                direction = "improving (falling)" if labor_score > 0 else "deteriorating (rising)" if labor_score < 0 else "flat"
                evidence.append(
                    f"Unemployment rate is {direction} (latest={unrate_ds.payload.get('latest_value')} "
                    f"as of {unrate_ds.payload.get('latest_date')})"
                )
                if direction.startswith("deteriorating"):
                    risks.append("Rising unemployment raises recession risk and growth concerns")
                elif direction.startswith("improving"):
                    catalysts.append("Resilient labor market supports the soft-landing/growth thesis")

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
            data_gaps=[],  # filled in by BaseAgent.analyze() for missing/blocked datasets
        )
