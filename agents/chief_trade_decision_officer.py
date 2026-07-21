"""
Chief Trade Decision Officer — orchestrates the Institutional Trade
Decision Engine described in the platform upgrade spec.

Architecturally similar to agents/chief_strategy_officer.py: it fetches no
data of its own from DataIntegrityManager, it only reads AgentReports that
other departments already produced. Where it differs on purpose (per spec
section 1): the Chief Strategy Officer's job is to COLLAPSE every
department into one overall_market_score. This agent's job is the
opposite — keep Fundamental, Technical, and Risk as three independently
computed, independently visible scores all the way through, and gate
execution decisions on the RELATIONSHIP between them (via the entry
confirmation checklist), never on one blended number. See
agents/trade_scoring.py for exactly how that separation is enforced.

Runs entirely alongside agents/chief_strategy_officer.py and
agents/chief_execution_officer.py, not in place of them — a workflow can
use either pipeline, or both, from the same underlying AgentReports.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from models.report import AgentReport
from models.open_trade import OpenTrade
from models.trade_decision import TradeDecision, TradeHealth

from . import trade_scoring
from .score_momentum import compute_score_momentum, explain_momentum
from .trade_lifecycle_officer import evaluate_lifecycle


class ChiefTradeDecisionOfficer:
    department = "Chief Trade Decision Officer"

    def __init__(self, report_store=None):
        """
        report_store: optional database.report_store.ReportStore. If
        provided, used for (a) score momentum, reading prior
        trade_decisions rows for this asset, and (b) checking for an open
        trade to run lifecycle evaluation against. Momentum and lifecycle
        both degrade gracefully to "insufficient history" / "not open"
        when no store is given — this agent still works standalone (e.g.
        in tests) without a database.
        """
        self.report_store = report_store

    def decide(self, asset_or_theme: str, reports: List[AgentReport], current_price: Optional[float] = None) -> TradeDecision:
        technical_report = next(
            (r for r in reports if r.department == trade_scoring.TECHNICAL_DEPARTMENT), None,
        )

        fund_score, fund_contrib, fund_excluded = trade_scoring.fundamental_score(reports)
        tech_score, tech_contrib, tech_excluded = trade_scoring.technical_score(technical_report)
        risk_score_value, risk_contrib, risk_excluded = trade_scoring.risk_score(reports)
        overall = trade_scoring.overall_score(fund_score, tech_score, risk_score_value)

        entry_confirmation = trade_scoring.build_entry_confirmation(technical_report, fund_score, risk_score_value)
        rating = trade_scoring.execution_rating(fund_score, tech_score, risk_score_value, entry_confirmation)
        grade = trade_scoring.trade_grade(overall, fund_score, tech_score, risk_score_value)

        contributing = list(dict.fromkeys(fund_contrib + tech_contrib + risk_contrib))
        excluded = list(dict.fromkeys(fund_excluded + tech_excluded + risk_excluded))

        catalysts = list(dict.fromkeys(c for r in reports for c in r.catalysts))[:8]
        risks = list(dict.fromkeys(r2 for r in reports for r2 in r.risks))[:8]

        fund_momentum = self._momentum(asset_or_theme, "fundamental_score", fund_score, catalysts, risks)
        tech_momentum = self._momentum(asset_or_theme, "technical_score", tech_score, catalysts, risks)
        risk_momentum = self._momentum(asset_or_theme, "risk_score", risk_score_value, catalysts, risks)
        overall_momentum = self._momentum(asset_or_theme, "overall_score", overall, catalysts, risks)

        trade_health, conviction = self._lifecycle(
            asset_or_theme, technical_report, fund_score, risk_score_value, current_price,
        )

        explanation = self._build_explanation(
            asset_or_theme, fund_score, tech_score, risk_score_value, rating, entry_confirmation,
        )

        decision = TradeDecision(
            asset_or_theme=asset_or_theme,
            fundamental_score=fund_score,
            technical_score=tech_score,
            risk_score=risk_score_value,
            overall_score=overall,
            fundamental_momentum=fund_momentum,
            technical_momentum=tech_momentum,
            risk_momentum=risk_momentum,
            overall_momentum=overall_momentum,
            entry_confirmation=entry_confirmation,
            execution_rating=rating,
            trade_grade=grade,
            trade_health=trade_health,
            institutional_conviction=conviction,
            decision_explanation=explanation,
            key_catalysts=catalysts,
            key_risks=risks,
            contributing_departments=contributing,
            excluded_departments=excluded,
        )

        if self.report_store is not None:
            self.report_store.save_trade_decision(decision)

        return decision

    def _momentum(self, asset_or_theme, score_field, current_score, catalysts, risks):
        if self.report_store is None:
            from models.trade_decision import ScoreMomentum
            return ScoreMomentum()
        history = self.report_store.get_trade_decisions(asset_or_theme=asset_or_theme, limit=500)
        momentum = compute_score_momentum(history, score_field, current_score)
        momentum.explanation = explain_momentum(momentum.momentum, catalysts, risks)
        return momentum

    def _lifecycle(self, asset_or_theme, technical_report, fund_score, risk_score_value, current_price):
        if self.report_store is None:
            return TradeHealth.NOT_OPEN, ""

        open_trade_row = self.report_store.get_open_trade(asset_or_theme)
        if open_trade_row is None:
            return TradeHealth.NOT_OPEN, ""

        from datetime import datetime
        from models.open_trade import TradeDirection

        open_trade = OpenTrade(
            id=open_trade_row["id"],
            asset_or_theme=open_trade_row["asset_or_theme"],
            direction=TradeDirection(open_trade_row["direction"]),
            entry_technical_bias_score=open_trade_row["entry_technical_bias_score"],
            entry_fundamental_bias_score=open_trade_row["entry_fundamental_bias_score"],
            entry_risk_score=open_trade_row["entry_risk_score"],
            entry_market_structure_note=open_trade_row["entry_market_structure_note"],
            stop_loss_level=open_trade_row["stop_loss_level"],
            entry_price=open_trade_row["entry_price"],
            opened_at=datetime.fromisoformat(open_trade_row["opened_at"]),
        )

        health, reasons = evaluate_lifecycle(
            open_trade, technical_report, fund_score, risk_score_value, current_price,
        )
        conviction = {
            TradeHealth.EXCELLENT: "High",
            TradeHealth.HEALTHY: "Moderate-High",
            TradeHealth.WEAKENING: "Moderate",
            TradeHealth.CRITICAL: "Low",
        }.get(health, "")
        return health, conviction

    def _build_explanation(self, asset_or_theme, fund_score, tech_score, risk_score_value, rating, entry_confirmation) -> str:
        fund_lean = "bullish" if fund_score > 55 else "bearish" if fund_score < 45 else "neutral"
        tech_state = (
            "confirmed" if entry_confirmation.market_structure_confirmed
            else "not yet confirmed"
        )
        from models.trade_decision import EXECUTION_RATING_LABELS
        parts = [
            f"{asset_or_theme}: Fundamentals are {fund_lean} ({fund_score:.0f}/100), "
            f"technical structure is {tech_state} ({tech_score:.0f}/100), "
            f"Risk Score is {risk_score_value:.0f}/100.",
            f"Recommended action: {EXECUTION_RATING_LABELS[rating]}.",
        ]
        failed = entry_confirmation.failed_checks()
        if failed and rating.value != "enter_now":
            parts.append("Outstanding requirements: " + ", ".join(f.replace('_', ' ') for f in failed) + ".")
        return " ".join(parts)
