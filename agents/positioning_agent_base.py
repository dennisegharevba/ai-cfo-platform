"""
PositioningAgent: shared logic for agents whose signal is CFTC COT
positioning. Chief Commodity Analyst and Chief FX Analyst are both thin
subclasses of this for Phase 3 — each just sets `department`.

Unlike the Chief Macro Officer / Chief Bond Strategist (Phase 2), these
agents are instantiated per-market (you construct one ChiefCommodityAnalyst
per commodity, e.g. Gold, Crude Oil, Corn) since the underlying COT dataset
key is market-specific.

Updated after Phase 3's initial release to blend TWO positioning signals
rather than only speculative:
    - Speculative (non-commercial) net position trend, 60% weight —
      trend-following, useful for momentum/crowd-risk reads
    - Commercial (producer/hedger) net position trend, 40% weight —
      reflects real hedging exposure, often read as a structural
      "smart money" signal
Both use the same underlying net_position_trend_score function (see
agents/positioning_scoring.py), just pointed at different fields.

Updated again to route the relationship between those two signals through
the Institutional Relationship Engine (agents/institutional_relationship.py)
rather than a single ad-hoc divergence check: neither commercials nor
speculators are ever treated as "right" on their own — their agreement or
disagreement is classified (Full Alignment / Mild Divergence / Strong
Divergence) and that classification adjusts CONFIDENCE, never the
direction of the bias score itself, per that module's docstring.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .positioning_scoring import net_position_trend_score, positioning_extremity_flag
from .institutional_relationship import (
    classify_alignment, apply_confidence_adjustment, describe_alignment, AlignmentStatus,
)

WEIGHT_SPECULATIVE = 60
WEIGHT_COMMERCIAL = 40


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
        risk_level = RiskLevel.MODERATE

        component_scores: List[float] = []
        component_weights: List[float] = []
        spec_trend = None
        comm_trend = None

        if ds is not None:
            history = ds.payload.get("history", [])

            spec_trend = net_position_trend_score(history, long_key="noncomm_long", short_key="noncomm_short")
            if spec_trend is not None:
                component_scores.append(spec_trend)
                component_weights.append(WEIGHT_SPECULATIVE)
                direction = (
                    "building net length" if spec_trend > 0
                    else "reducing length / building shorts" if spec_trend < 0
                    else "roughly unchanged"
                )
                evidence.append(
                    f"Speculators have been {direction} in {asset_or_theme} "
                    f"positioning over the last {len(history)} COT reports "
                    f"(latest report date: {ds.payload.get('report_date')})"
                )
                if spec_trend > 0:
                    catalysts.append("Building speculative length reflects growing bullish conviction")
                elif spec_trend < 0:
                    risks.append("Speculators reducing length or adding shorts signals waning bullish conviction")

            comm_trend = net_position_trend_score(history, long_key="comm_long", short_key="comm_short")
            if comm_trend is not None:
                component_scores.append(comm_trend)
                component_weights.append(WEIGHT_COMMERCIAL)
                direction = (
                    "building net length" if comm_trend > 0
                    else "reducing length / building shorts" if comm_trend < 0
                    else "roughly unchanged"
                )
                evidence.append(f"Commercials (hedgers) have been {direction} over the same window")
                if comm_trend > 0:
                    catalysts.append("Commercial hedgers building net length is a constructive structural signal")
                elif comm_trend < 0:
                    risks.append("Commercial hedgers reducing net length is a cautionary structural signal")

            # --- Institutional Relationship Engine: classify agreement/
            # disagreement between commercials and speculators, and let
            # that classification adjust confidence (never the direction). ---
            alignment_status = classify_alignment(spec_trend, comm_trend)
            if alignment_status is not None:
                description = describe_alignment(alignment_status)
                evidence.append(description["evidence"])
                if description["risk"]:
                    risks.append(description["risk"])
                if description["catalyst"]:
                    catalysts.append(description["catalyst"])
                if alignment_status == AlignmentStatus.STRONG_DIVERGENCE:
                    risk_level = RiskLevel.ELEVATED

            if not component_scores:
                risks.append("Insufficient COT history to compute a positioning trend")

            extremity = positioning_extremity_flag(ds.payload)
            if extremity == "crowded_long":
                risk_level = RiskLevel.ELEVATED
                risks.append("Net speculative positioning is a crowded long — vulnerable to a sharp reversal")
            elif extremity == "crowded_short":
                risk_level = RiskLevel.ELEVATED
                risks.append("Net speculative positioning is a crowded short — vulnerable to a short-covering rally")

        if component_scores:
            total_weight = sum(component_weights)
            bias_score = sum(s * w for s, w in zip(component_scores, component_weights)) / total_weight
            confidence = 40.0 + (30.0 * len(component_scores))  # 40 base, +30 per component (max 100 with both)
            confidence = apply_confidence_adjustment(confidence, alignment_status)
        else:
            bias_score = 0.0
            confidence = 0.0

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
