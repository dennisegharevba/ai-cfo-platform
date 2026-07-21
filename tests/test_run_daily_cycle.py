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
    """Sanity check: every key mentioned in either watchlist resolves to a
    real DEPARTMENT_RUNNERS entry, so a typo in the config would be caught
    here rather than silently skipping a department in production."""
    from config.watchlist import WATCHLIST_DAILY, WATCHLIST_WEEKLY
    used_keys = {
        dept_key
        for watchlist in (WATCHLIST_DAILY, WATCHLIST_WEEKLY)
        for entry in watchlist
        for dept_key in entry["departments"]
    }
    for key in used_keys:
        assert key in DEPARTMENT_RUNNERS, f"'{key}' used in a watchlist has no matching runner"


def test_daily_watchlist_has_no_duplicate_assets():
    from config.watchlist import WATCHLIST_DAILY
    assets = [entry["asset_or_theme"] for entry in WATCHLIST_DAILY]
    assert len(assets) == len(set(assets))


def test_weekly_watchlist_covers_a_large_ticker_universe():
    from config.watchlist import WATCHLIST_WEEKLY
    assets = [entry["asset_or_theme"] for entry in WATCHLIST_WEEKLY]
    assert len(assets) == len(set(assets))  # no duplicate tickers
    assert len(assets) > 300  # genuinely broad, not a token handful


def test_equity_runner_resolves_cik_automatically(monkeypatch):
    """The equity department no longer requires a hand-entered 'cik' param —
    it resolves one via the ticker/CIK lookup, using the exact fake payload
    shape connectors.sec_ticker_lookup.resolve_cik expects."""
    import scripts.run_daily_cycle as cycle_module

    def _fake_resolve_cik(manager, ticker, user_agent):
        return "0000320193" if ticker == "AAPL" else None

    monkeypatch.setattr(cycle_module, "resolve_cik", _fake_resolve_cik)
    monkeypatch.setattr(cycle_module, "SEC_EQUITY_COURTESY_DELAY_SECONDS", 0.0)

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    report = cycle_module._run_equity(manager, "AAPL", {})

    # No live network here, so the report itself will be zero-confidence —
    # what matters is that it resolved a CIK and registered real connectors
    # under it without raising, rather than requiring params["cik"].
    assert manager.is_registered("SEC_AAPL_EPS")
    assert manager.is_registered("SEC_AAPL_REV")
    assert report.asset_or_theme == "AAPL"


def test_equity_runner_degrades_gracefully_when_ticker_not_found(monkeypatch):
    import scripts.run_daily_cycle as cycle_module

    monkeypatch.setattr(cycle_module, "resolve_cik", lambda manager, ticker, user_agent: None)
    monkeypatch.setattr(cycle_module, "SEC_EQUITY_COURTESY_DELAY_SECONDS", 0.0)

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    report = cycle_module._run_equity(manager, "NOSUCHTICKER", {})

    assert report.confidence == 0.0
    assert report.is_degraded() is True
