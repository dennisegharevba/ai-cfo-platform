from models.report import AgentReport, Bias, RiskLevel
from models.strategy_report import StrategyReport
from database.report_store import ReportStore


def _agent_report(department="Chief Macro Officer", asset="Gold", bias_score=50.0, confidence=80.0):
    return AgentReport(
        department=department,
        asset_or_theme=asset,
        bias=Bias.BULLISH,
        bias_score=bias_score,
        confidence=confidence,
        risk_level=RiskLevel.MODERATE,
        catalysts=["Some catalyst"],
        risks=["Some risk"],
        evidence=["Some evidence"],
        data_gaps=[],
    )


def _strategy_report(asset="Gold", overall_score=70.0, confidence=60.0):
    return StrategyReport(
        asset_or_theme=asset,
        overall_market_score=overall_score,
        confidence_score=confidence,
        risk_level=RiskLevel.ELEVATED,
        bias=Bias.BULLISH,
        bias_score=40.0,
        trade_thesis="Test thesis",
        investment_committee_summary="Test summary",
        catalysts=["Cat A"],
        risks=["Risk A"],
        invalidation_notes=["Note A"],
        contributing_departments=["Chief Macro Officer"],
        excluded_departments=[],
    )


def test_save_and_retrieve_agent_report():
    store = ReportStore(":memory:")
    report_id = store.save_agent_report(_agent_report())
    assert report_id == 1

    rows = store.get_agent_reports()
    assert len(rows) == 1
    assert rows[0]["department"] == "Chief Macro Officer"
    assert rows[0]["asset_or_theme"] == "Gold"
    assert rows[0]["catalysts"] == ["Some catalyst"]  # JSON round-tripped back to a list
    assert rows[0]["bias_score"] == 50.0


def test_get_agent_reports_filters_by_department():
    store = ReportStore(":memory:")
    store.save_agent_report(_agent_report(department="Chief Macro Officer"))
    store.save_agent_report(_agent_report(department="Chief Bond Strategist"))

    macro_only = store.get_agent_reports(department="Chief Macro Officer")
    assert len(macro_only) == 1
    assert macro_only[0]["department"] == "Chief Macro Officer"


def test_get_agent_reports_filters_by_asset():
    store = ReportStore(":memory:")
    store.save_agent_report(_agent_report(asset="Gold"))
    store.save_agent_report(_agent_report(asset="Silver"))

    gold_only = store.get_agent_reports(asset_or_theme="Gold")
    assert len(gold_only) == 1
    assert gold_only[0]["asset_or_theme"] == "Gold"


def test_get_agent_reports_respects_limit_and_newest_first():
    store = ReportStore(":memory:")
    store.save_agent_report(_agent_report(bias_score=10.0))
    store.save_agent_report(_agent_report(bias_score=20.0))
    store.save_agent_report(_agent_report(bias_score=30.0))

    rows = store.get_agent_reports(limit=2)
    assert len(rows) == 2
    assert rows[0]["bias_score"] == 30.0  # newest first
    assert rows[1]["bias_score"] == 20.0


def test_save_and_retrieve_strategy_report():
    store = ReportStore(":memory:")
    report_id = store.save_strategy_report(_strategy_report())
    assert report_id == 1

    rows = store.get_strategy_reports()
    assert len(rows) == 1
    assert rows[0]["trade_thesis"] == "Test thesis"
    assert rows[0]["contributing_departments"] == ["Chief Macro Officer"]


def test_execution_readiness_and_institutional_commentary_round_trip():
    store = ReportStore(":memory:")
    report = _strategy_report()
    report.execution_readiness = "high_conviction"
    report.institutional_commentary = "Test commentary explaining why."
    store.save_strategy_report(report)

    rows = store.get_strategy_reports()
    assert rows[0]["execution_readiness"] == "high_conviction"
    assert rows[0]["institutional_commentary"] == "Test commentary explaining why."


def test_migration_adds_new_columns_to_pre_upgrade_database(tmp_path):
    """
    Simulates a real database file created BEFORE the Institutional
    Relationship Engine upgrade (no execution_readiness/institutional_
    commentary columns), proving ReportStore._migrate() adds them rather
    than every subsequent insert failing with "no such column".
    """
    import sqlite3

    db_path = str(tmp_path / "pre_upgrade.db")

    # Build a strategy_reports table matching the OLD schema (no new columns).
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE strategy_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_or_theme TEXT NOT NULL,
            overall_market_score REAL NOT NULL,
            confidence_score REAL NOT NULL,
            risk_level TEXT NOT NULL,
            bias TEXT NOT NULL,
            bias_score REAL NOT NULL,
            trade_thesis TEXT NOT NULL,
            investment_committee_summary TEXT NOT NULL,
            catalysts TEXT NOT NULL,
            risks TEXT NOT NULL,
            invalidation_notes TEXT NOT NULL,
            contributing_departments TEXT NOT NULL,
            excluded_departments TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    # Opening it via ReportStore should migrate it in place, not error.
    store = ReportStore(db_path)
    report_id = store.save_strategy_report(_strategy_report())
    assert report_id == 1

    rows = store.get_strategy_reports()
    assert rows[0]["execution_readiness"] == ""  # DEFAULT '' from the migration
    store.close()


def test_record_and_retrieve_outcome():
    store = ReportStore(":memory:")
    strategy_id = store.save_strategy_report(_strategy_report())
    store.record_outcome(strategy_id, realized_return_pct=3.5, was_correct=True, notes="Worked out")

    outcomes = store.get_outcomes(strategy_report_id=strategy_id)
    assert len(outcomes) == 1
    assert outcomes[0]["realized_return_pct"] == 3.5
    assert outcomes[0]["was_correct"] == 1
    assert outcomes[0]["notes"] == "Worked out"


def test_outcome_with_none_values_stored_correctly():
    store = ReportStore(":memory:")
    strategy_id = store.save_strategy_report(_strategy_report())
    store.record_outcome(strategy_id)  # no realized_return_pct or was_correct yet

    outcomes = store.get_outcomes(strategy_report_id=strategy_id)
    assert outcomes[0]["realized_return_pct"] is None
    assert outcomes[0]["was_correct"] is None


def test_data_persists_across_multiple_operations_same_store_instance():
    store = ReportStore(":memory:")
    for i in range(5):
        store.save_agent_report(_agent_report(bias_score=float(i)))
    assert len(store.get_agent_reports(limit=100)) == 5


def test_separate_store_instances_do_not_share_in_memory_data():
    store1 = ReportStore(":memory:")
    store1.save_agent_report(_agent_report())
    store2 = ReportStore(":memory:")
    assert store2.get_agent_reports() == []  # independent in-memory DBs
