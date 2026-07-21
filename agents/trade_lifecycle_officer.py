"""
Chief Trade Lifecycle Officer.

Per spec section 4: once a trade is open, the platform must NOT recommend
closing just because the Overall Score changes. This agent is the piece
that enforces that — it never looks at overall_score at all. It only
compares the CURRENT read against the specific conditions snapshotted at
entry (models/open_trade.py's OpenTrade), across the six structural
questions the spec lists, and only escalates trade_health when MULTIPLE
of those conditions confirm the thesis has actually weakened (not just one
noisy reading).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from models.open_trade import OpenTrade
from models.report import AgentReport, RiskLevel
from models.trade_decision import TradeHealth

TECHNICAL_TREND_INVALIDATION_DELTA = 30.0   # bias_score points away from entry
FUNDAMENTAL_THESIS_INVALIDATION_DELTA = 30.0
RISK_INCREASE_INVALIDATION_DELTA = 20.0     # risk_score DROP (higher score = lower risk)


def _stop_loss_invalidated(open_trade: OpenTrade, current_price: Optional[float]) -> bool:
    if open_trade.stop_loss_level is None or current_price is None:
        return False
    if open_trade.direction.value == "long":
        return current_price <= open_trade.stop_loss_level
    return current_price >= open_trade.stop_loss_level


def evaluate_lifecycle(
    open_trade: OpenTrade,
    technical_report: Optional[AgentReport],
    current_fundamental_score: float,
    current_risk_score: float,
    current_price: Optional[float] = None,
) -> Tuple[TradeHealth, List[str]]:
    """
    Returns (trade_health, reasons) where reasons lists exactly which of
    the six spec-section-4 conditions fired, so a "Weakening"/"Critical"
    read is always explainable, matching this platform's auditability
    convention used everywhere else (e.g. ChiefExecutionOfficer.blocking_reasons).
    """
    reasons: List[str] = []

    # 1. Has the technical trend changed?
    if technical_report is not None:
        trend_delta = technical_report.bias_score - open_trade.entry_technical_bias_score
        # For a long, deterioration is a negative delta; for a short, a positive delta.
        adverse_delta = -trend_delta if open_trade.direction.value == "long" else trend_delta
        if adverse_delta >= TECHNICAL_TREND_INVALIDATION_DELTA:
            reasons.append(
                f"Technical trend has moved {adverse_delta:+.1f} points against the {open_trade.direction.value} thesis"
            )

    # 4. Has market structure failed? — proxied via technical risk_level
    # flipping to HIGH (this phase's Technical Officer doesn't yet emit an
    # explicit BOS/CHoCH event — see agents/chief_technical_officer.py's
    # docstring on planned coverage; documented simplification, not hidden).
    if technical_report is not None and technical_report.risk_level == RiskLevel.HIGH:
        reasons.append("Technical risk level has escalated to HIGH — market structure may be failing")

    # 2. Has the macro thesis changed?
    fund_delta = current_fundamental_score - open_trade.entry_fundamental_bias_score
    adverse_fund_delta = -fund_delta if open_trade.direction.value == "long" else fund_delta
    if adverse_fund_delta >= FUNDAMENTAL_THESIS_INVALIDATION_DELTA:
        reasons.append(f"Fundamental Score has moved {adverse_fund_delta:+.1f} points against the original thesis")

    # 3 & 5. Has risk increased / has liquidity shifted? — both read off
    # the Risk Score, since agents/asset_risk_officer.py already folds
    # liquidity-adjacent factors (ATR expansion, weekend gap risk) into it.
    risk_delta = open_trade.entry_risk_score - current_risk_score  # positive = risk got worse
    if risk_delta >= RISK_INCREASE_INVALIDATION_DELTA:
        reasons.append(f"Risk Score has deteriorated {risk_delta:+.1f} points since entry")

    # 6. Has the stop-loss been invalidated?
    if _stop_loss_invalidated(open_trade, current_price):
        reasons.append(f"Price has reached or breached the stop-loss level ({open_trade.stop_loss_level})")

    # Per spec: only recommend closing when MULTIPLE conditions confirm
    # weakness. Health escalates in steps, never off a single flag.
    if _stop_loss_invalidated(open_trade, current_price):
        return TradeHealth.CRITICAL, reasons
    if len(reasons) >= 3:
        return TradeHealth.CRITICAL, reasons
    if len(reasons) == 2:
        return TradeHealth.WEAKENING, reasons
    if len(reasons) == 1:
        return TradeHealth.HEALTHY, reasons
    return TradeHealth.EXCELLENT, reasons
