"""
StrategyReport: the Chief Strategy Officer's output.

Deliberately a separate model from AgentReport rather than a reuse of it —
the Strategy Officer's job per the spec produces things no single
department's report has a field for: a trade thesis, an investment
committee summary, and which departments were actually included vs.
excluded from the synthesis. Reusing AgentReport and bolting extra fields
onto it would blur "one department's independent read" with "the
synthesized cross-department verdict" — worth keeping visibly distinct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from .report import Bias, RiskLevel


@dataclass
class StrategyReport:
    asset_or_theme: str
    overall_market_score: float      # 0-100 (50 = neutral), per the spec's "Overall Market Score"
    confidence_score: float          # 0-100
    risk_level: RiskLevel
    bias: Bias
    bias_score: float                # -100..+100, the same scale every department uses
    trade_thesis: str
    investment_committee_summary: str
    catalysts: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    invalidation_notes: List[str] = field(default_factory=list)
    contributing_departments: List[str] = field(default_factory=list)
    excluded_departments: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "asset_or_theme": self.asset_or_theme,
            "overall_market_score": self.overall_market_score,
            "confidence_score": self.confidence_score,
            "risk_level": self.risk_level.value,
            "bias": self.bias.value,
            "bias_score": self.bias_score,
            "trade_thesis": self.trade_thesis,
            "investment_committee_summary": self.investment_committee_summary,
            "catalysts": self.catalysts,
            "risks": self.risks,
            "invalidation_notes": self.invalidation_notes,
            "contributing_departments": self.contributing_departments,
            "excluded_departments": self.excluded_departments,
            "generated_at": self.generated_at.isoformat(),
        }
