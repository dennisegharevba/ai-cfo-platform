"""
Chief Learning Officer.

A fourth architectural shape, distinct from the three established so far:
- BaseAgent / PortfolioAgent produce a fresh AgentReport from live data.
- ChiefStrategyOfficer produces a StrategyReport from other agents' reports.
- ChiefLearningOfficer produces NEITHER — it is a sink other agents write
  their reports into, and a query engine for performance analytics over
  everything that's been recorded. It has no "analyze" method at all.

Per the spec: "Store every report, every alert, every trade thesis,
confidence score, outcome. Generate performance analytics to improve
future scoring." The storage half is database/report_store.py (SQLite,
free, stdlib-only); this class adds the analytics half on top.

Outcomes are recorded from OBSERVED market results, never from any trade
the platform placed — this platform never trades automatically (see the
top-level README) — so "was_correct" reflects whether reality moved the
way the synthesized bias said it would, as judged and entered by whoever
reviews the thesis later.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.report import AgentReport
from models.strategy_report import StrategyReport

from database.report_store import ReportStore


class ChiefLearningOfficer:
    department = "Chief Learning Officer"

    def __init__(self, store: Optional[ReportStore] = None, db_path: str = "ai_cfo_platform.db"):
        self.store = store or ReportStore(db_path)

    # ------------------------------------------------------------------ #
    # Recording (thin pass-through to ReportStore — kept here so callers
    # only ever need to depend on ChiefLearningOfficer, not the storage
    # layer directly)
    # ------------------------------------------------------------------ #
    def record_agent_report(self, report: AgentReport) -> int:
        return self.store.save_agent_report(report)

    def record_strategy_report(self, report: StrategyReport) -> int:
        return self.store.save_strategy_report(report)

    def record_outcome(
        self,
        strategy_report_id: int,
        realized_return_pct: Optional[float] = None,
        was_correct: Optional[bool] = None,
        notes: str = "",
    ) -> int:
        return self.store.record_outcome(strategy_report_id, realized_return_pct, was_correct, notes)

    # ------------------------------------------------------------------ #
    # Performance analytics
    # ------------------------------------------------------------------ #
    def department_performance_summary(self, department: Optional[str] = None, limit: int = 1000) -> Dict[str, Any]:
        """
        Summary stats for a department's historical reports (or across all
        departments if none specified): report count, average confidence,
        bias distribution, and how often the department was working with
        degraded/incomplete data.
        """
        reports = self.store.get_agent_reports(department=department, limit=limit)
        if not reports:
            return {
                "department": department or "ALL",
                "report_count": 0,
                "average_confidence": 0.0,
                "bias_distribution": {},
                "degraded_report_pct": 0.0,
            }

        total = len(reports)
        avg_confidence = sum(r["confidence"] for r in reports) / total

        bias_distribution: Dict[str, int] = {}
        for r in reports:
            bias_distribution[r["bias"]] = bias_distribution.get(r["bias"], 0) + 1

        degraded_count = sum(1 for r in reports if len(r["data_gaps"]) > 0)

        return {
            "department": department or "ALL",
            "report_count": total,
            "average_confidence": round(avg_confidence, 1),
            "bias_distribution": bias_distribution,
            "degraded_report_pct": round(100.0 * degraded_count / total, 1),
        }

    def strategy_accuracy_summary(self, asset_or_theme: Optional[str] = None, limit: int = 1000) -> Dict[str, Any]:
        """
        Win-rate and average realized return across every strategy report
        that has a recorded outcome. Strategy reports with no recorded
        outcome yet are excluded rather than counted as failures — an
        unreviewed thesis isn't a wrong one.
        """
        strategy_reports = self.store.get_strategy_reports(asset_or_theme=asset_or_theme, limit=limit)

        judged_outcomes: List[Dict[str, Any]] = []
        for sr in strategy_reports:
            for outcome in self.store.get_outcomes(strategy_report_id=sr["id"]):
                if outcome["was_correct"] is not None:
                    judged_outcomes.append(outcome)

        if not judged_outcomes:
            return {
                "asset_or_theme": asset_or_theme or "ALL",
                "judged_outcome_count": 0,
                "win_rate_pct": None,
                "average_realized_return_pct": None,
            }

        wins = sum(1 for o in judged_outcomes if o["was_correct"] == 1)
        win_rate = 100.0 * wins / len(judged_outcomes)

        returns = [o["realized_return_pct"] for o in judged_outcomes if o["realized_return_pct"] is not None]
        avg_return = sum(returns) / len(returns) if returns else None

        return {
            "asset_or_theme": asset_or_theme or "ALL",
            "judged_outcome_count": len(judged_outcomes),
            "win_rate_pct": round(win_rate, 1),
            "average_realized_return_pct": round(avg_return, 2) if avg_return is not None else None,
        }
