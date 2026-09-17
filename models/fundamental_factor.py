"""
FundamentalFactor / CategoryScore: the data models behind the Institutional
Fundamental Scoring Engine.

Per the upgrade spec, the platform no longer produces a market bias
primarily from COT — instead, every major macroeconomic/fundamental
factor is evaluated INDEPENDENTLY (its own current/previous/forecast/
surprise/bias/weight/confidence/timestamp/source) before contributing to
a category-level score, which in turn contributes to the overall
synthesis (agents.chief_strategy_officer.ChiefStrategyOfficer, unchanged).

This is an ADDITIVE layer, not a replacement of the existing AgentReport
pipeline: agents.chief_macro_officer.ChiefMacroOfficer (the first
department upgraded to use this) still produces a standard AgentReport
(so ChiefStrategyOfficer/ChiefLearningOfficer/ChiefExecutionOfficer all
keep working completely unchanged), but that AgentReport now ALSO carries
the full per-factor breakdown in its `factor_breakdown` field (see
models/report.py) for anything that wants to show the detailed,
hedge-fund-terminal-style view.

Honest scope note: `forecast_value` and `surprise` are frequently None —
this platform has no free, reliable source of economist consensus
forecasts (FRED and similar free sources report ACTUAL published values,
not forecasts). Fields are Optional precisely so this is visible and
explicit rather than papered over with a fabricated number. See
docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from .report import Bias, RiskLevel


class FactorBias(str, Enum):
    """
    A simple tri-state bias for a SINGLE factor line item — deliberately
    coarser than the platform-wide 5-level Bias enum (models.report.Bias),
    matching the spec's explicit ask for "Bullish / Bearish / Neutral
    status" per factor. Category-level and department-level bias still use
    the existing 5-level Bias (via bias_from_score) for consistency with
    every other AgentReport in the platform.
    """
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


def factor_bias_from_score(score: float, neutral_band: float = 10.0) -> FactorBias:
    """Map a -100..+100 factor score onto the tri-state FactorBias. Pass a
    wider/narrower neutral_band per factor type if the default 10-point
    band isn't appropriate for that factor's typical noise level."""
    if score > neutral_band:
        return FactorBias.BULLISH
    if score < -neutral_band:
        return FactorBias.BEARISH
    return FactorBias.NEUTRAL


@dataclass
class FundamentalFactor:
    """One independently-scored factor line (e.g. "Core CPI (YoY)")."""

    name: str                                  # e.g. "Core CPI (YoY)"
    category: str                              # e.g. "Macroeconomic"
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    forecast_value: Optional[float] = None      # None when no free forecast source exists — see module docstring
    score: float = 0.0                          # -100..+100, this factor's own directional read
    bias: FactorBias = FactorBias.NEUTRAL
    importance_weight: float = 5.0              # 1-10 scale, per the spec (NOT 0-100)
    confidence: float = 0.0                     # 0-100
    source: str = ""                            # e.g. "FRED"
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: List[str] = field(default_factory=list)

    @property
    def surprise(self) -> Optional[float]:
        """current - forecast, only when both are known — never fabricated."""
        if self.current_value is None or self.forecast_value is None:
            return None
        return self.current_value - self.forecast_value

    @property
    def change_from_previous(self) -> Optional[float]:
        if self.current_value is None or self.previous_value is None:
            return None
        return self.current_value - self.previous_value

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "forecast_value": self.forecast_value,
            "surprise": self.surprise,
            "change_from_previous": self.change_from_previous,
            "score": self.score,
            "bias": self.bias.value,
            "importance_weight": self.importance_weight,
            "confidence": self.confidence,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
            "notes": self.notes,
        }


@dataclass
class CategoryScore:
    """
    Aggregate of every FundamentalFactor within one category (e.g. every
    Macro factor) into a single category-level score/confidence/bias —
    computed by agents.fundamental_scoring_engine.score_category().
    """

    category: str
    factors: List[FundamentalFactor] = field(default_factory=list)
    category_score: float = 0.0                 # -100..+100
    category_confidence: float = 0.0            # 0-100
    bias: Bias = Bias.NEUTRAL
    risk_level: RiskLevel = RiskLevel.MODERATE
    disagreement: float = 0.0                    # weighted stdev across factor scores

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "factors": [f.to_dict() for f in self.factors],
            "category_score": self.category_score,
            "category_confidence": self.category_confidence,
            "bias": self.bias.value,
            "risk_level": self.risk_level.value,
            "disagreement": self.disagreement,
        }
