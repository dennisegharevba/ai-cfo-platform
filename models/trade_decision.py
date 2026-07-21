"""
TradeDecision: the Chief Trade Decision Officer's output.

This is the model that makes the platform's core new principle structurally
enforceable: Fundamental, Technical, and Risk are stored as THREE SEPARATE
fields (fundamental_score, technical_score, risk_score), not collapsed into
one number before this model is built. overall_score exists too (the
spec's weighted 40/40/20 blend) but nothing downstream is allowed to act on
overall_score alone — execution_rating is derived from the entry-confirmation
checklist (models.trade_decision.EntryConfirmation), not from overall_score
directly. See agents/chief_trade_decision_officer.py for exactly how each
field is produced.

Deliberately a NEW model rather than extra fields bolted onto StrategyReport
(models/strategy_report.py) — StrategyReport is the Chief Strategy Officer's
"what does the platform think" synthesis (Phase 7, already in production
use via dashboard/pages/3_Strategy_Synthesis.py and scripts/run_daily_cycle.py).
TradeDecision answers a different question — "should a human act on this,
and how" — and per the spec must NOT be derivable by just re-reading
StrategyReport.overall_market_score. Keeping them separate models makes that
architectural boundary something a type-checker (and a future maintainer)
can see, not just a convention someone has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class ExecutionRating(str, Enum):
    ENTER_NOW = "enter_now"
    WAIT_FOR_CONFIRMATION = "wait_for_confirmation"
    WATCHLIST = "watchlist"
    AVOID = "avoid"


EXECUTION_RATING_LABELS = {
    ExecutionRating.ENTER_NOW: "🟢 ENTER NOW",
    ExecutionRating.WAIT_FOR_CONFIRMATION: "🟡 WAIT FOR TECHNICAL CONFIRMATION",
    ExecutionRating.WATCHLIST: "🔵 WATCHLIST",
    ExecutionRating.AVOID: "🔴 AVOID",
}


class TradeGrade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    C = "C"
    D = "D"


class Momentum(str, Enum):
    STRENGTHENING = "strengthening"
    STABLE = "stable"
    WEAKENING = "weakening"
    MAJOR_DETERIORATION = "major_deterioration"
    INSUFFICIENT_HISTORY = "insufficient_history"


class TradeHealth(str, Enum):
    EXCELLENT = "excellent"
    HEALTHY = "healthy"
    WEAKENING = "weakening"
    CRITICAL = "critical"
    NOT_OPEN = "not_open"  # no open position exists for this asset


@dataclass
class EntryConfirmation:
    """
    Section 8 of the spec: every requirement must be individually checked
    and individually visible, so "WAIT FOR CONFIRMATION" is always
    explainable by pointing at exactly which requirement(s) failed —
    matching this platform's existing auditability convention (see
    agents/chief_execution_officer.py's blocking_reasons).
    """
    trend_alignment: bool = False
    market_structure_confirmed: bool = False
    breakout_confirmed: bool = False
    volume_confirmed: bool = False
    liquidity_confirmed: bool = False
    macro_alignment: bool = False
    risk_acceptable: bool = False
    minimum_rr_achieved: bool = False
    notes: List[str] = field(default_factory=list)  # which checks failed, and why

    def all_passed(self) -> bool:
        return all([
            self.trend_alignment, self.market_structure_confirmed, self.breakout_confirmed,
            self.volume_confirmed, self.liquidity_confirmed, self.macro_alignment,
            self.risk_acceptable, self.minimum_rr_achieved,
        ])

    def failed_checks(self) -> List[str]:
        checks = {
            "trend_alignment": self.trend_alignment,
            "market_structure_confirmed": self.market_structure_confirmed,
            "breakout_confirmed": self.breakout_confirmed,
            "volume_confirmed": self.volume_confirmed,
            "liquidity_confirmed": self.liquidity_confirmed,
            "macro_alignment": self.macro_alignment,
            "risk_acceptable": self.risk_acceptable,
            "minimum_rr_achieved": self.minimum_rr_achieved,
        }
        return [name for name, passed in checks.items() if not passed]


@dataclass
class ScoreMomentum:
    """One component score's movement over standard institutional windows."""
    previous_score: Optional[float] = None
    change_1h: Optional[float] = None
    change_4h: Optional[float] = None
    change_24h: Optional[float] = None
    change_weekly: Optional[float] = None
    momentum: Momentum = Momentum.INSUFFICIENT_HISTORY
    explanation: List[str] = field(default_factory=list)  # e.g. "Commercial hedgers reduced longs"


@dataclass
class TradeDecision:
    asset_or_theme: str

    # --- Section 1-2: three independent scores, never collapsed pre-storage ---
    fundamental_score: float          # 0-100, 40% weight
    technical_score: float            # 0-100, 40% weight
    risk_score: float                 # 0-100, 20% weight (higher = LOWER risk, per spec)
    overall_score: float              # 0-100, the documented 0.4/0.4/0.2 blend

    # --- Section 3: momentum, one ScoreMomentum per component + overall ---
    fundamental_momentum: ScoreMomentum = field(default_factory=ScoreMomentum)
    technical_momentum: ScoreMomentum = field(default_factory=ScoreMomentum)
    risk_momentum: ScoreMomentum = field(default_factory=ScoreMomentum)
    overall_momentum: ScoreMomentum = field(default_factory=ScoreMomentum)

    # --- Section 5-6: execution rating and trade grade ---
    entry_confirmation: EntryConfirmation = field(default_factory=EntryConfirmation)
    execution_rating: ExecutionRating = ExecutionRating.AVOID
    trade_grade: TradeGrade = TradeGrade.D

    # --- Section 7: position management (populated only if a trade is open) ---
    trade_health: TradeHealth = TradeHealth.NOT_OPEN
    institutional_conviction: str = ""  # short qualitative label, e.g. "High", "Moderate"

    # --- Section 9-10: explanation & dashboard fields ---
    decision_explanation: str = ""
    key_catalysts: List[str] = field(default_factory=list)
    key_risks: List[str] = field(default_factory=list)
    contributing_departments: List[str] = field(default_factory=list)
    excluded_departments: List[str] = field(default_factory=list)

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "asset_or_theme": self.asset_or_theme,
            "fundamental_score": self.fundamental_score,
            "technical_score": self.technical_score,
            "risk_score": self.risk_score,
            "overall_score": self.overall_score,
            "execution_rating": self.execution_rating.value,
            "trade_grade": self.trade_grade.value,
            "trade_health": self.trade_health.value,
            "institutional_conviction": self.institutional_conviction,
            "decision_explanation": self.decision_explanation,
            "key_catalysts": self.key_catalysts,
            "key_risks": self.key_risks,
            "contributing_departments": self.contributing_departments,
            "excluded_departments": self.excluded_departments,
            "entry_confirmation_failed_checks": self.entry_confirmation.failed_checks(),
            "generated_at": self.generated_at.isoformat(),
        }
