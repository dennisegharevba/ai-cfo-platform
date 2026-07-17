"""
Chief Bond Strategist.

Scope for Phase 2 (starting point — 5Y/30Y and credit spreads slot into this
same agent in a later phase without changing the architecture):

    - DGS10 (10-Year Treasury yield)
    - DGS2  (2-Year Treasury yield)

Produces a bias on BOND PRICES (not yields directly) since that's what a
strategist ultimately trades: rising yields => falling bond prices => bearish
for bond prices, and vice versa. Also flags yield curve inversion (10Y-2Y < 0)
as an elevated-risk recession signal, per the spec's explicit yield curve
coverage requirement.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, Bias, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .chief_macro_officer import _series_trend_score  # shared trend-scoring helper

KEY_DGS10 = "FRED_DGS10"
KEY_DGS2 = "FRED_DGS2"


def _latest_float(dataset: Optional[Dataset]) -> Optional[float]:
    if dataset is None:
        return None
    try:
        return float(dataset.payload.get("latest_value"))
    except (TypeError, ValueError):
        return None


class ChiefBondStrategist(BaseAgent):
    department = "Chief Bond Strategist"

    def required_dataset_keys(self) -> List[str]:
        return [KEY_DGS10, KEY_DGS2]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        catalysts: List[str] = []
        evidence: List[str] = []
        risks: List[str] = []

        dgs10_ds = usable.get(KEY_DGS10)
        dgs2_ds = usable.get(KEY_DGS2)

        # Bond-price bias: rising yields are bearish for bond prices, so we
        # invert the raw yield trend (lower_is_bullish=False on the yield
        # itself means "yield rising" -> bearish for price -> pass True to
        # flip it into a bond-price-oriented score).
        bias_score = 0.0
        component_count = 0

        if dgs10_ds is not None:
            yield_trend = _series_trend_score(dgs10_ds.payload.get("history", []), lower_is_bullish=False)
            if yield_trend is not None:
                price_score = -yield_trend  # rising yield -> falling bond price
                bias_score += price_score
                component_count += 1
                latest = dgs10_ds.payload.get("latest_value")
                direction = "rising" if yield_trend > 0 else "falling" if yield_trend < 0 else "flat"
                evidence.append(f"10Y Treasury yield is {direction} (latest={latest}%)")
                if direction == "rising":
                    risks.append("Rising 10Y yields pressure bond prices and duration-sensitive assets")
                elif direction == "falling":
                    catalysts.append("Falling 10Y yields are supportive of bond prices")

        if component_count:
            bias_score = bias_score / component_count

        # Yield curve check (10Y - 2Y), independent of the price-bias score above.
        y10 = _latest_float(dgs10_ds)
        y2 = _latest_float(dgs2_ds)
        risk_level = RiskLevel.MODERATE
        if y10 is not None and y2 is not None:
            spread = y10 - y2
            evidence.append(f"10Y-2Y yield curve spread is {spread:+.2f}pp")
            if spread < 0:
                risk_level = RiskLevel.HIGH
                risks.append("Inverted yield curve (10Y-2Y < 0) is a historically reliable recession signal")
            elif spread < 0.25:
                risk_level = RiskLevel.ELEVATED
                risks.append("Flattening yield curve warrants close monitoring for inversion risk")

        confidence = 40.0 + (30.0 * component_count)  # 40 base, +30 for the one scorable component (max 70 here)
        if len(usable) < len(self.required_dataset_keys()):
            confidence = max(0.0, confidence - 15.0)
            if risk_level == RiskLevel.MODERATE:
                risk_level = RiskLevel.ELEVATED
        if component_count == 0:
            confidence = 0.0
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
