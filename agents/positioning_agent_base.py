"""
PositioningAgent: shared logic for agents whose signal is CFTC COT
positioning. Chief Commodity Analyst and Chief FX Analyst are both thin
subclasses of this — each just sets `department`.

Unlike the Chief Macro Officer / Chief Bond Strategist, these agents are
instantiated per-market (you construct one ChiefCommodityAnalyst per
commodity, e.g. Gold, Crude Oil, Corn) since the underlying COT dataset key
is market-specific.

Per an explicit later decision, Commercial Traders were REMOVED as a
directional input entirely. Commercial positioning no longer influences
bias, confidence, or the overall market score — anywhere. Primary emphasis
is now on Non-Commercial Traders (Large Speculators), on the reasoning
that they're more representative of trend-following institutional capital
that drives medium- to long-term price movements. See
docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md for the full account.

The bias score is now 100% driven by Non-Commercial (speculative) net
position trend (agents.positioning_scoring.net_position_trend_score).
Layered on top, via agents/speculative_positioning_analysis.py:
    - Weekly (week-over-week) momentum in that same speculative positioning
    - A percentile rank of the current net position against the fetched
      history window, flagging positioning extremes
    - A continuation/reversal classification combining the two

Commercial positioning can still be shown as a purely INFORMATIONAL,
non-scoring line — gated behind config.settings.ENABLE_COMMERCIAL_POSITIONING_DISPLAY
(defaults to disabled) — but even when enabled it is computed independently
and never feeds into bias_score or confidence, matching the explicit
directive that Commercial data must never influence scores regardless of
whether it's displayed.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .positioning_scoring import net_position_trend_score, positioning_extremity_flag
from .risk_severity import worse_risk_level
from .speculative_positioning_analysis import (
    net_positions_series, latest_weekly_change, percentile_rank,
    classify_extreme_percentile, classify_momentum_signal,
)
from config.settings import ENABLE_COMMERCIAL_POSITIONING_DISPLAY

# Confidence model (single-component: Non-Commercial only).
BASE_CONFIDENCE = 55.0
MOMENTUM_CONTINUATION_BONUS = 15.0
MOMENTUM_REVERSAL_PENALTY = -15.0
EXTREME_PERCENTILE_PENALTY = -10.0

_EXTREME_LABEL_TEXT = {
    "extreme_bullish": "an extreme bullish reading",
    "extreme_bearish": "an extreme bearish reading",
}


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

        spec_trend = None
        confidence = 0.0

        if ds is not None:
            history = ds.payload.get("history", [])

            spec_trend = net_position_trend_score(history, long_key="noncomm_long", short_key="noncomm_short")
            weekly_change = latest_weekly_change(history)
            pct = percentile_rank(history)
            nets = net_positions_series(history)
            current_net = nets[0] if nets else None
            extreme_label = classify_extreme_percentile(pct)
            momentum_signal = classify_momentum_signal(spec_trend, weekly_change, current_net)

            if spec_trend is not None:
                direction = (
                    "building net length" if spec_trend > 0
                    else "reducing length / building shorts" if spec_trend < 0
                    else "roughly unchanged"
                )
                evidence.append(
                    f"Non-Commercial (large speculator) positioning has been {direction} in "
                    f"{asset_or_theme} over the last {len(history)} COT reports "
                    f"(latest report date: {ds.payload.get('report_date')})"
                )
                if spec_trend > 0:
                    catalysts.append("Building Non-Commercial length reflects growing bullish conviction")
                elif spec_trend < 0:
                    risks.append("Non-Commercial traders reducing length or adding shorts signals waning bullish conviction")

                confidence = BASE_CONFIDENCE

                if weekly_change is not None:
                    wdir = "increasing" if weekly_change > 0 else "decreasing" if weekly_change < 0 else "unchanged"
                    evidence.append(
                        f"Non-Commercial net position changed by {weekly_change:+,.0f} contracts over the "
                        f"past week ({wdir})"
                    )

                if pct is not None:
                    extreme_text = _EXTREME_LABEL_TEXT.get(extreme_label, "within a normal range for this window")
                    evidence.append(
                        f"Current Non-Commercial net position is at the {pct:.0f}th percentile of the last "
                        f"{len(nets)} COT reports ({extreme_text}) — this measures where TODAY's position sits "
                        f"within its own recent range, a separate question from the overall multi-week TREND "
                        f"reported above; the two can genuinely disagree (e.g. a severe multi-week reversal "
                        f"that hasn't yet pushed the position to a new extreme within this specific window)"
                    )
                    if extreme_label is not None:
                        risks.append(
                            f"Non-Commercial positioning shows {extreme_text} relative to its own recent "
                            f"history — elevated risk of a positioning-driven reversal"
                        )
                        confidence += EXTREME_PERCENTILE_PENALTY

                if momentum_signal == "continuation":
                    catalysts.append("Weekly Non-Commercial positioning change confirms the broader multi-week trend")
                    confidence += MOMENTUM_CONTINUATION_BONUS
                elif momentum_signal == "reversal_watch":
                    risks.append(
                        "Weekly Non-Commercial positioning change is moving opposite the broader multi-week "
                        "trend — a potential early trend-reversal signal"
                    )
                    confidence += MOMENTUM_REVERSAL_PENALTY

                if extreme_label is not None and momentum_signal == "reversal_watch":
                    risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)

                confidence = max(0.0, min(100.0, confidence))
            else:
                risks.append("Insufficient COT history to compute a Non-Commercial positioning trend")

            extremity = positioning_extremity_flag(ds.payload)
            if extremity == "crowded_long":
                risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)
                risks.append("Net Non-Commercial positioning is a crowded long — vulnerable to a sharp reversal")
            elif extremity == "crowded_short":
                risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)
                risks.append("Net Non-Commercial positioning is a crowded short — vulnerable to a short-covering rally")

            # --- Optional, informational-only Commercial display ---
            # Gated behind a config flag that defaults to OFF. Even when
            # enabled, this is computed independently and NEVER folded into
            # bias_score or confidence above — see module docstring and
            # docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md.
            if ENABLE_COMMERCIAL_POSITIONING_DISPLAY:
                comm_trend = net_position_trend_score(history, long_key="comm_long", short_key="comm_short")
                if comm_trend is not None:
                    comm_direction = (
                        "building net length" if comm_trend > 0
                        else "reducing length / building shorts" if comm_trend < 0
                        else "roughly unchanged"
                    )
                    evidence.append(
                        f"[Informational only, not used in scoring] Commercial (hedger) positioning has "
                        f"been {comm_direction} over the same window"
                    )

        bias_score = spec_trend if spec_trend is not None else 0.0

        if confidence == 0.0:
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
