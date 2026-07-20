from datetime import datetime, timezone

from scripts.run_daily_cycle import run_cycle, DEPARTMENT_RUNNERS
from core.data_source import DataSource, DataSourceError
from core.refresh_manager import DataIntegrityManager
from agents.chief_learning_officer import ChiefLearningOfficer
from agents.chief_execution_officer import ChiefExecutionOfficer
from database.report_store import ReportStore


class FakeFredLikeSource(DataSource):
    """A FRED-shaped source that always succeeds with a strongly bullish read."""
    name = "FAKE_FRED"
    default_ttl_seconds = 300

    def fetch(self, **kwargs):
        payload = {
            "series_id": "TEST",
            "latest_value": "300",
            "latest_date": "2026-06-01",
            "history": [{"value": "300", "date": "2026-06-01"}, {"value": "320", "date": "2026-05-01"}],
        }
        return payload, datetime.now(timezone.utc)


class FakeFailingSource(DataSource):
    name = "FAKE_FAILING"
    default_ttl_seconds = 300

    def fetch(self, **kwargs):
        raise DataSourceError("simulated outage")


def _patched_macro_runner(manager, asset, params):
    """Bypass real FRED connectors — register fakes under the same keys the real runner uses."""
    from agents.chief_macro_officer import ChiefMacroOfficer, KEY_CPI, KEY_UNRATE
    if not manager.is_registered(KEY_CPI):
        manager.register(KEY_CPI, primary=FakeFredLikeSource())
    if not manager.is_registered(KEY_UNRATE):
        manager.register(KEY_UNRATE, primary=FakeFredLikeSource())
    return ChiefMacroOfficer(manager, min_quality=50.0).analyze(asset)


def test_successful_watchlist_entry_is_recorded_and_summarized(monkeypatch):
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "macro", _patched_macro_runner)
    watchlist = [{"asset_or_theme": "Test Asset", "departments": {"macro": {}}}]

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    results = run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    assert len(results) == 1
    assert results[0]["asset"] == "Test Asset"
    assert results[0]["error"] is None
    assert results[0]["department_count"] == 1
    assert len(learning_officer.store.get_agent_reports()) == 1
    assert len(learning_officer.store.get_strategy_reports()) == 1


def test_one_failing_asset_does_not_stop_the_rest(monkeypatch):
    def _failing_runner(manager, asset, params):
        raise RuntimeError("boom — this asset's processing blew up")

    monkeypatch.setitem(DEPARTMENT_RUNNERS, "macro", _patched_macro_runner)
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "broken", _failing_runner)

    watchlist = [
        {"asset_or_theme": "Broken Asset", "departments": {"broken": {}}},
        {"asset_or_theme": "Good Asset", "departments": {"macro": {}}},
    ]

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    results = run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    assert len(results) == 2
    assert results[0]["asset"] == "Broken Asset"
    assert results[0]["error"] is not None
    assert results[1]["asset"] == "Good Asset"
    assert results[1]["error"] is None  # NOT affected by the first entry's failure


def test_unknown_department_key_is_skipped_not_fatal():
    watchlist = [{"asset_or_theme": "Test Asset", "departments": {"nonexistent_department": {}}}]
    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    results = run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    assert len(results) == 1
    assert results[0]["error"] is None  # skipped gracefully, still synthesizes (with zero reports)
    assert results[0]["department_count"] == 0


def test_empty_watchlist_returns_empty_results():
    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)
    results = run_cycle([], manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)
    assert results == []


def test_all_department_runner_keys_have_a_real_handler():
    """Sanity check: every key mentioned in config/watchlist.py resolves to
    a real DEPARTMENT_RUNNERS entry, so a typo in the watchlist config would
    be caught here rather than silently skipping a department in production."""
    from config.watchlist import WATCHLIST
    used_keys = {dept_key for entry in WATCHLIST for dept_key in entry["departments"]}
    for key in used_keys:
        assert key in DEPARTMENT_RUNNERS, f"'{key}' used in WATCHLIST has no matching runner"
