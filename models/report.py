"""
AgentReport: the standard output every Chief Officer agent produces.

Per the platform spec, each department's analysis must include, at minimum:
    - a bullish/bearish directional score
    - a confidence score
    - a risk assessment
    - key catalysts
    - the underlying evidence, in plain language

Keeping this as one shared model (rather than each agent inventing its own
shape) is what lets the Chief Strategy Officer (Phase 7) mechanically collect
reports from every department and reconcile them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional


class Bias(str, Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"


@dataclass
class AgentReport:
    department: str                 # e.g. "Chief Macro Officer"
    asset_or_theme: str              # e.g. "USD", "10Y Treasury", "Gold"
    bias: Bias
    bias_score: float                # -100 (max bearish) to +100 (max bullish)
    confidence: float                # 0-100 — how confident the agent is in this bias
    risk_level: RiskLevel
    catalysts: List[str] = field(default_factory=list)     # key drivers behind the call
    risks: List[str] = field(default_factory=list)          # what would invalidate/threaten the thesis
    evidence: List[str] = field(default_factory=list)       # plain-language supporting facts
    data_gaps: List[str] = field(default_factory=list)      # datasets that were unusable/blocked
    # Added alongside the Institutional Fundamental Scoring Engine upgrade
    # (see docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md) — the full
    # per-factor breakdown, one models.fundamental_factor.FundamentalFactor
    # per entry, for departments that compute one. Typed as List[Any]
    # rather than importing FundamentalFactor directly, since that module
    # imports Bias/RiskLevel FROM this one — importing it back here would
    # be circular. Defaults to empty so every existing AgentReport
    # construction (every department not yet upgraded to the new engine)
    # keeps working completely unchanged.
    factor_breakdown: List[Any] = field(default_factory=list)
    # Added alongside the Institutional Market Regime Filters upgrade (see
    # docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md) — the full
    # agents.institutional_market_regime.InstitutionalMarketRegime result,
    # for departments that compute one (Chief Macro Officer). Defaults to
    # None so every other department's AgentReport construction keeps
    # working completely unchanged.
    market_regime: Optional[Any] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_degraded(self) -> bool:
        """True if this report was produced with one or more data gaps."""
        return len(self.data_gaps) > 0

    def to_dict(self) -> dict:
        return {
            "department": self.department,
            "asset_or_theme": self.asset_or_theme,
            "bias": self.bias.value,
            "bias_score": self.bias_score,
            "confidence": self.confidence,
            "risk_level": self.risk_level.value,
            "catalysts": self.catalysts,
            "risks": self.risks,
            "evidence": self.evidence,
            "data_gaps": self.data_gaps,
            "factor_breakdown": [f.to_dict() for f in self.factor_breakdown],
            "market_regime": self.market_regime.to_dict() if self.market_regime is not None else None,
            "generated_at": self.generated_at.isoformat(),
        }


def bias_from_score(score: float) -> Bias:
    """Map a -100..+100 bias_score onto the Bias enum with consistent thresholds."""
    if score >= 60:
        return Bias.STRONGLY_BULLISH
    if score >= 15:
        return Bias.BULLISH
    if score > -15:
        return Bias.NEUTRAL
    if score > -60:
        return Bias.BEARISH
    return Bias.STRONGLY_BEARISH
