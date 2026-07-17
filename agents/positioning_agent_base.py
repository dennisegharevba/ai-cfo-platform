"""
PositioningAgent: shared logic for agents whose primary signal is CFTC COT
speculative positioning trend. Chief Commodity Analyst and Chief FX Analyst
are both thin subclasses of this for Phase 3 — each just sets `department`.

Unlike the Chief Macro Officer / Chief Bond Strategist (Phase 2), these
agents are instantiated per-market (you construct one ChiefCommodityAnalyst
per commodity, e.g. Gold, Crude Oil, Corn) since the underlying COT dataset
key is market-specific.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .positioning_scoring import net_position_trend_score, positioning_extremity_flag


class PositioningAgent(BaseAgent):
    department = "UNSET"  # subclasses must override

    def __init__(self, manager, cot_key: str, min_quality: float = 60.0):
        """
        cot_key: the key this market's COT data was registered under in the
        DataIntegrityManager, e.g. "COT_GOLD", "COT_EUR_FX".
        """
        super().__init__(manager, min_quality)
        self.cot_key = cot_key

    def required_dataset_keys(self) -> List[str]:
        return [self.cot_key]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        ds = usable.get(self.cot_key)
        evidence: List[str] = []
        catalysts: List[str] = []
        risks: List[str] = []
        bias_score = 0.0
        risk_level = RiskLevel.MODERATE
        confidence = 0.0

        if ds is not None:
            history = ds.payload.get("history", [])
            trend_score = net_position_trend_score(history)

            if trend_score is not None:
                bias_score = trend_score
                confidence = 70.0
                direction = (
                    "building net length" if trend_score > 0
                    else "reducing length / building shorts" if trend_score < 0
                    else "roughly unchanged"
                )
                evidence.append(
                    f"Speculators have been {direction} in {asset_or_theme} "
                    f"positioning over the last {len(history)} COT reports "
                    f"(latest report date: {ds.payload.get('report_date')})"
                )
                if trend_score > 0:
                    catalysts.append("Building speculative length reflects growing bullish conviction")
                elif trend_score < 0:
                    risks.append("Speculators reducing length or adding shorts signals waning bullish conviction")
            else:
                risks.append("Insufficient COT history to compute a positioning trend")

            extremity = positioning_extremity_flag(ds.payload)
            if extremity == "crowded_long":
                risk_level = RiskLevel.ELEVATED
                risks.append("Net speculative positioning is a crowded long — vulnerable to a sharp reversal")
            elif extremity == "crowded_short":
                risk_level = RiskLevel.ELEVATED
                risks.append("Net speculative positioning is a crowded short — vulnerable to a short-covering rally")

        if ds is None or confidence == 0.0:
            risk_level = RiskLevel.HIGH

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
