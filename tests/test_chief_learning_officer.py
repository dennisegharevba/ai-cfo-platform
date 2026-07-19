from agents.chief_learning_officer import ChiefLearningOfficer
from database.report_store import ReportStore
from models.report import AgentReport, Bias, RiskLevel
from models.strategy_report import StrategyReport


def _agent_report(department="Chief Macro Officer", bias=Bias.BULLISH, confidence=80.0, data_gaps=None):
    return AgentReport(
        department=department,
        asset_or_theme="Gold",
        bias=bias,
        bias_score=50.0,
        confidence=confidence,
        risk_level=RiskLevel.MODERATE,
        data_gaps=data_gaps or [],
    )


def _strategy_report(asset="Gold"):
    return StrategyReport(
        asset_or_theme=asset,
        overall_market_score=70.0,
        confidence_score=60.0,
        risk_level=RiskLevel.ELEVATED,
        bias=Bias.BULLISH,
        bias_score=40.0,
        trade_thesis="Test thesis",
        investment_committee_summary="Test summary",
    )


def _officer():
    return ChiefLearningOfficer(store=ReportStore(":memory:"))


def test_record_agent_report_returns_id():
    officer = _officer()
    report_id = officer.record_agent_report(_agent_report())
    assert report_id == 1


def test_record_strategy_report_and_outcome():
    officer = _officer()
    sr_id = officer.record_strategy_report(_strategy_report())
    outcome_id = officer.record_outcome(sr_id, realized_return_pct=2.5, was_correct=True)
    assert outcome_id == 1


def test_department_performance_summary_empty_store():
    officer = _officer()
    summary = officer.department_performance_summary("Chief Macro Officer")
    assert summary["report_count"] == 0
    assert summary["average_confidence"] == 0.0
    assert summary["bias_distribution"] == {}


def test_department_performance_summary_computes_averages_and_distribution():
    officer = _officer()
    officer.record_agent_report(_agent_report(bias=Bias.BULLISH, confidence=80.0))
    officer.record_agent_report(_agent_report(bias=Bias.BULLISH, confidence=60.0))
    officer.record_agent_report(_agent_report(bias=Bias.BEARISH, confidence=40.0))

    summary = officer.department_performance_summary("Chief Macro Officer")
    assert summary["report_count"] == 3
    assert summary["average_confidence"] == 60.0  # (80+60+40)/3
    assert summary["bias_distribution"] == {"bullish": 2, "bearish": 1}


def test_department_performance_summary_tracks_degraded_reports():
    officer = _officer()
    officer.record_agent_report(_agent_report(data_gaps=[]))
    officer.record_agent_report(_agent_report(data_gaps=["SOME_KEY (missing)"]))

    summary = officer.department_performance_summary("Chief Macro Officer")
    assert summary["degraded_report_pct"] == 50.0


def test_department_performance_summary_filters_by_department():
    officer = _officer()
    officer.record_agent_report(_agent_report(department="Chief Macro Officer"))
    officer.record_agent_report(_agent_report(department="Chief Bond Strategist"))

    summary = officer.department_performance_summary("Chief Macro Officer")
    assert summary["report_count"] == 1


def test_strategy_accuracy_summary_no_outcomes_yet():
    officer = _officer()
    officer.record_strategy_report(_strategy_report())
    summary = officer.strategy_accuracy_summary()
    assert summary["judged_outcome_count"] == 0
    assert summary["win_rate_pct"] is None


def test_strategy_accuracy_summary_computes_win_rate_and_avg_return():
    officer = _officer()
    sr1 = officer.record_strategy_report(_strategy_report())
    sr2 = officer.record_strategy_report(_strategy_report())
    sr3 = officer.record_strategy_report(_strategy_report())

    officer.record_outcome(sr1, realized_return_pct=5.0, was_correct=True)
    officer.record_outcome(sr2, realized_return_pct=-3.0, was_correct=False)
    officer.record_outcome(sr3, realized_return_pct=4.0, was_correct=True)

    summary = officer.strategy_accuracy_summary()
    assert summary["judged_outcome_count"] == 3
    assert abs(summary["win_rate_pct"] - 66.7) < 0.1
    assert abs(summary["average_realized_return_pct"] - 2.0) < 0.01  # (5-3+4)/3


def test_strategy_accuracy_summary_excludes_unjudged_outcomes():
    officer = _officer()
    sr1 = officer.record_strategy_report(_strategy_report())
    sr2 = officer.record_strategy_report(_strategy_report())

    officer.record_outcome(sr1, realized_return_pct=5.0, was_correct=True)
    officer.record_outcome(sr2)  # not yet judged — no was_correct

    summary = officer.strategy_accuracy_summary()
    assert summary["judged_outcome_count"] == 1  # sr2's unjudged outcome is excluded
    assert summary["win_rate_pct"] == 100.0


def test_strategy_accuracy_summary_filters_by_asset():
    officer = _officer()
    sr_gold = officer.record_strategy_report(_strategy_report(asset="Gold"))
    sr_silver = officer.record_strategy_report(_strategy_report(asset="Silver"))
    officer.record_outcome(sr_gold, was_correct=True)
    officer.record_outcome(sr_silver, was_correct=False)

    gold_summary = officer.strategy_accuracy_summary(asset_or_theme="Gold")
    assert gold_summary["judged_outcome_count"] == 1
    assert gold_summary["win_rate_pct"] == 100.0
