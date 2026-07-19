"""
Phase 8 demo: takes illustrative department reports (same style as
scripts/demo_strategy_officer.py from Phase 7), records every one of them
plus the synthesized StrategyReport through the Chief Learning Officer,
then simulates a few historical cycles with recorded outcomes to show the
performance-analytics queries working.

Like demo_strategy_officer.py, this uses illustrative example data rather
than live-fetched data — the Learning Officer's job (persistence +
analytics) doesn't depend on live market access to demonstrate, and a
meaningful performance summary needs a history of outcomes that can't
exist on a single, just-fetched cycle anyway.

Run:
    python scripts/demo_learning_officer.py

Uses an in-memory SQLite database, so nothing is written to disk — pass a
real db_path to ReportStore/ChiefLearningOfficer to persist across runs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.chief_learning_officer import ChiefLearningOfficer
from agents.chief_strategy_officer import ChiefStrategyOfficer
from database.report_store import ReportStore
from models.report import AgentReport, RiskLevel, bias_from_score


def _report(department, bias_score, confidence, risk_level=RiskLevel.MODERATE, asset="Gold"):
    return AgentReport(
        department=department, asset_or_theme=asset, bias=bias_from_score(bias_score),
        bias_score=bias_score, confidence=confidence, risk_level=risk_level,
    )


def main():
    print("\n=== AI CFO Platform — Phase 8: Chief Learning Officer demo ===\n")

    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    strategy_officer = ChiefStrategyOfficer()

    # Simulate 3 historical research cycles for Gold, each with slightly
    # different department reports, each recorded + synthesized + judged.
    cycles = [
        {
            "reports": [_report("Chief Macro Officer", 60, 80), _report("Chief Technical Officer", 40, 70)],
            "realized_return_pct": 4.2, "was_correct": True,
        },
        {
            "reports": [_report("Chief Macro Officer", -50, 75), _report("Chief Technical Officer", -30, 65)],
            "realized_return_pct": -2.1, "was_correct": True,
        },
        {
            "reports": [_report("Chief Macro Officer", 55, 70), _report("Chief Technical Officer", -60, 80)],
            "realized_return_pct": -1.5, "was_correct": False,
        },
    ]

    for i, cycle in enumerate(cycles, start=1):
        for report in cycle["reports"]:
            learning_officer.record_agent_report(report)

        synthesis = strategy_officer.synthesize("Gold", cycle["reports"])
        strategy_id = learning_officer.record_strategy_report(synthesis)
        learning_officer.record_outcome(
            strategy_id, realized_return_pct=cycle["realized_return_pct"], was_correct=cycle["was_correct"],
        )
        print(f"Cycle {i}: bias={synthesis.bias.value}, score={synthesis.bias_score:+.1f}, "
              f"confidence={synthesis.confidence_score:.0f} -> "
              f"realized {cycle['realized_return_pct']:+.1f}% ({'correct' if cycle['was_correct'] else 'incorrect'})")

    print("\n=== Department performance summary: Chief Macro Officer ===")
    print(learning_officer.department_performance_summary("Chief Macro Officer"))

    print("\n=== Department performance summary: Chief Technical Officer ===")
    print(learning_officer.department_performance_summary("Chief Technical Officer"))

    print("\n=== Strategy accuracy summary: Gold ===")
    print(learning_officer.strategy_accuracy_summary(asset_or_theme="Gold"))


if __name__ == "__main__":
    main()
