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


def _fake_commodity_runner(manager, asset, params):
    """A minimal, fixed-neutral non-macro/non-sentiment department report —
    stands in for a real commodity/FX department so tests don't need real
    COT data just to prove the broad-context merge happened."""
    from models.report import AgentReport, Bias, RiskLevel
    return AgentReport(
        department="Chief Commodity Analyst", asset_or_theme=asset,
        bias=Bias.NEUTRAL, bias_score=0.0, confidence=60.0, risk_level=RiskLevel.MODERATE,
    )


def test_macro_report_is_merged_into_every_other_assets_synthesis(monkeypatch):
    """
    Update, 2026-09-18: confirmed real gap — Chief Macro Officer's report
    was previously only ever synthesized under its own "US Macro Outlook"
    watchlist entry, never merged into any other asset's own `reports`
    before strategy_officer.synthesize(), despite
    agents/trade_scoring.py's FUNDAMENTAL_DEPARTMENTS and
    agents/chief_strategy_officer.py's own docstring both expecting it.
    "US Macro Outlook" runs first in the watchlist here (matching
    config/watchlist.py's real ordering), so by the time "Gold" is
    processed, Chief Macro Officer's report should already be available
    to merge in.
    """
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "macro", _patched_macro_runner)
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "commodity", _fake_commodity_runner)
    watchlist = [
        {"asset_or_theme": "US Macro Outlook", "departments": {"macro": {}}},
        {"asset_or_theme": "Gold", "departments": {"commodity": {}}},
    ]

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    results = run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    gold_result = next(r for r in results if r["asset"] == "Gold")
    # Gold's own watchlist entry declares exactly 1 department ("commodity")
    # — department_count of 2 proves Chief Macro Officer's report was
    # actually merged in before synthesis, not just present in the cycle.
    assert gold_result["department_count"] == 2

    gold_strategy_reports = learning_officer.store.get_strategy_reports(asset_or_theme="Gold")
    assert "Chief Macro Officer" in gold_strategy_reports[0]["contributing_departments"]

    # The merge must never re-persist Chief Macro Officer's report a
    # second time under "Gold" — it was already recorded once, when the
    # "US Macro Outlook" entry produced it.
    macro_agent_reports = [
        r for r in learning_officer.store.get_agent_reports() if r["department"] == "Chief Macro Officer"
    ]
    assert len(macro_agent_reports) == 1


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


def test_risk_fundamentals_department_excluded_from_bias_weighting_in_real_cycle(monkeypatch):
    """
    A real end-to-end proof that "risk_fundamentals" is correctly routed
    through ChiefStrategyOfficer's risk_reports parameter (excluded from
    bias weighting, but still escalates risk_level) — not just tested in
    isolation on ChiefStrategyOfficer itself. A bearish-scored risk report
    alongside a bullish macro report should still leave the overall bias
    bullish, with risk_level escalated.
    """
    from models.report import RiskLevel

    monkeypatch.setitem(DEPARTMENT_RUNNERS, "macro", _patched_macro_runner)

    def _fake_risk_fundamentals_runner(manager, asset, params):
        from agents.chief_risk_fundamentals_officer import ChiefRiskFundamentalsOfficer
        # No price history registered -> honest zero-confidence/HIGH-risk
        # report, which is exactly the kind of "how risky" signal that
        # must never be allowed to drag bias toward neutral.
        return ChiefRiskFundamentalsOfficer(manager, ticker="NOTREGISTERED").analyze(asset)

    monkeypatch.setitem(DEPARTMENT_RUNNERS, "risk_fundamentals", _fake_risk_fundamentals_runner)

    watchlist = [{
        "asset_or_theme": "Test Asset",
        "departments": {"macro": {}, "risk_fundamentals": {}},
    }]
    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    results = run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    assert len(results) == 1
    assert results[0]["error"] is None
    assert results[0]["department_count"] == 2  # both departments counted, even though one is risk-routed
    assert results[0]["bias_score"] > 0  # bullish macro report, unaffected by the risk report's own bias
    assert results[0]["risk_level"] == RiskLevel.HIGH.value  # escalated by the risk report


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


def test_print_market_breadth_reads_only_price_history_keys(capsys):
    """
    Regression-style proof that _print_market_breadth correctly filters
    to PRICE_HISTORY_ prefixed keys only (ignoring any other registered
    dataset in the same manager, e.g. COT/FRED keys from the daily
    watchlist sharing the same manager instance) and computes real
    breadth from them — not just "doesn't crash."
    """
    import scripts.run_daily_cycle as cycle_module

    class FakePriceSource(DataSource):
        name = "FAKE_YAHOO"
        default_ttl_seconds = 3600

        def __init__(self, closes_oldest_first):
            self.closes = closes_oldest_first

        def fetch(self, **kwargs):
            newest_first = list(reversed(self.closes))
            history = [{"date": f"2026-06-{i+1:02d}", "close": c} for i, c in enumerate(newest_first)]
            return {"history": history}, datetime.now(timezone.utc)

    class FakeNonPriceSource(DataSource):
        name = "FAKE_OTHER"
        default_ttl_seconds = 3600

        def fetch(self, **kwargs):
            return {"latest_value": "1.0", "history": []}, datetime.now(timezone.utc)

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    manager.register("PRICE_HISTORY_AAPL", primary=FakePriceSource([100 + i * 0.5 for i in range(60)]))
    manager.register("PRICE_HISTORY_MSFT", primary=FakePriceSource([200 - i * 0.5 for i in range(60)]))
    manager.register("FRED_CPI", primary=FakeNonPriceSource())  # must NOT be swept into breadth

    cycle_module._print_market_breadth(manager)
    output = capsys.readouterr().out
    assert "Market Breadth" in output
    assert "2 of 2 large-cap tickers usable" in output
    assert "1 up / 1 down" in output


class _FakeCotSource(DataSource):
    """Returns a payload shaped like CotConnector's multi-week output —
    same fixture pattern as tests/test_chief_commodity_and_fx_analysts.py."""
    name = "FAKE_COT"
    default_ttl_seconds = 300

    def __init__(self, newest_first_net_pairs):
        """newest_first_net_pairs: list of (noncomm_long, noncomm_short), already newest-first."""
        self.pairs = newest_first_net_pairs

    def fetch(self, **kwargs):
        history = [
            {"report_date": f"2026-06-{i+1:02d}", "noncomm_long": str(l), "noncomm_short": str(s),
             "open_interest": "500000"}
            for i, (l, s) in enumerate(self.pairs)
        ]
        payload = {"market": "TEST MARKET", "history": history, **history[0]}
        return payload, datetime.now(timezone.utc)

    def validate_shape(self, payload):
        return isinstance(payload, dict) and len(payload.get("history", [])) > 0


def _reversal_commodity_runner(manager, asset, params):
    """A 'commodity' runner that registers a COT dataset showing a genuine
    reversal_watch (net had been building bullish, then this week dropped
    sharply) — same underlying data test_swing_signal.py's
    test_bearish_turn_on_reversal_against_bullish_trend uses."""
    from agents.chief_commodity_analyst import ChiefCommodityAnalyst
    key = f"COT_{params['cot_market']}"
    if not manager.is_registered(key):
        manager.register(key, primary=_FakeCotSource([(110000, 85000), (120000, 80000), (95000, 82000)]))
    return ChiefCommodityAnalyst(manager, cot_key=key, min_quality=50.0).analyze(asset)


def _continuation_commodity_runner(manager, asset, params):
    """A 'commodity' runner whose COT data is a plain continuation (no
    reversal) — should never produce a swing signal."""
    from agents.chief_commodity_analyst import ChiefCommodityAnalyst
    key = f"COT_{params['cot_market']}"
    if not manager.is_registered(key):
        manager.register(key, primary=_FakeCotSource([(140000, 85000), (120000, 80000), (95000, 82000)]))
    return ChiefCommodityAnalyst(manager, cot_key=key, min_quality=50.0).analyze(asset)


def _fake_sentiment_runner_factory(bias_score):
    def _runner(manager, asset, params):
        from models.report import AgentReport, Bias, RiskLevel, bias_from_score
        return AgentReport(
            department="Chief Sentiment Officer", asset_or_theme=asset, bias=bias_from_score(bias_score),
            bias_score=bias_score, confidence=55.0, risk_level=RiskLevel.MODERATE,
        )
    return _runner


def test_swing_signal_detected_and_persisted_on_real_reversal(monkeypatch):
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "commodity", _reversal_commodity_runner)
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "sentiment", _fake_sentiment_runner_factory(-40.0))

    watchlist = [
        {"asset_or_theme": "Broad Market Sentiment", "departments": {"sentiment": {}}},
        {"asset_or_theme": "Gold", "departments": {"commodity": {"cot_market": "GOLD"}}},
    ]
    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    signals = learning_officer.store.get_swing_signals(asset_or_theme="Gold")
    assert len(signals) == 1
    assert signals[0]["direction"] == "bearish_turn"
    assert signals[0]["news_alignment"] == "confirms"  # -40.0 news score agrees with the bearish turn


def test_no_swing_signal_on_continuation(monkeypatch):
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "commodity", _continuation_commodity_runner)
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "sentiment", _fake_sentiment_runner_factory(0.0))

    watchlist = [
        {"asset_or_theme": "Broad Market Sentiment", "departments": {"sentiment": {}}},
        {"asset_or_theme": "Gold", "departments": {"commodity": {"cot_market": "GOLD"}}},
    ]
    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=None)

    run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    assert learning_officer.store.get_swing_signals(asset_or_theme="Gold") == []


def test_swing_signal_triggers_telegram_alert_when_configured(monkeypatch):
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "commodity", _reversal_commodity_runner)
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "sentiment", _fake_sentiment_runner_factory(-40.0))

    sent_messages = []

    class FakeAlerter:
        def send_message(self, text, parse_mode="Markdown"):
            sent_messages.append(text)
            return {"ok": True}

    watchlist = [
        {"asset_or_theme": "Broad Market Sentiment", "departments": {"sentiment": {}}},
        {"asset_or_theme": "Gold", "departments": {"commodity": {"cot_market": "GOLD"}}},
    ]
    manager = DataIntegrityManager(min_quality_threshold=50.0)
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=FakeAlerter())

    run_cycle(watchlist, manager=manager, learning_officer=learning_officer, execution_officer=execution_officer)

    assert len(sent_messages) == 1
    assert "Gold" in sent_messages[0]
    signals = learning_officer.store.get_swing_signals(asset_or_theme="Gold")
    assert signals[0]["alert_sent"] is True


def test_swing_signal_not_re_alerted_within_the_same_cot_release_week(monkeypatch):
    """Running the cycle twice in a row (simulating two consecutive
    weekday scheduled runs against the same still-unrevised COT release)
    should only alert once — see agents.swing_signal.should_send_swing_alert."""
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "commodity", _reversal_commodity_runner)
    monkeypatch.setitem(DEPARTMENT_RUNNERS, "sentiment", _fake_sentiment_runner_factory(-40.0))

    sent_messages = []

    class FakeAlerter:
        def send_message(self, text, parse_mode="Markdown"):
            sent_messages.append(text)
            return {"ok": True}

    watchlist = [
        {"asset_or_theme": "Broad Market Sentiment", "departments": {"sentiment": {}}},
        {"asset_or_theme": "Gold", "departments": {"commodity": {"cot_market": "GOLD"}}},
    ]
    learning_officer = ChiefLearningOfficer(store=ReportStore(":memory:"))
    execution_officer = ChiefExecutionOfficer(alerter=FakeAlerter())

    # Two separate cycles (two separate managers, like two separate scheduled runs).
    run_cycle(watchlist, manager=DataIntegrityManager(min_quality_threshold=50.0),
              learning_officer=learning_officer, execution_officer=execution_officer)
    run_cycle(watchlist, manager=DataIntegrityManager(min_quality_threshold=50.0),
              learning_officer=learning_officer, execution_officer=execution_officer)

    assert len(sent_messages) == 1  # not two
    signals = learning_officer.store.get_swing_signals(asset_or_theme="Gold")
    assert len(signals) == 2  # both detections were still persisted...
    assert sum(1 for s in signals if s["alert_sent"]) == 1  # ...but only the first was alerted


def test_print_market_breadth_counts_requested_tickers_even_when_all_fail(capsys):
    """
    Regression test for a real bug caught before shipping: an earlier
    version pre-filtered to only USABLE datasets before computing breadth,
    so if every requested ticker failed to fetch, the summary would show
    the misleading "0 of 0 usable" (implying nothing was even attempted)
    instead of the honest "0 of N usable" (N tickers were genuinely
    requested; all of them failed). Proven directly with a source that
    always raises.
    """
    import scripts.run_daily_cycle as cycle_module
    from core.data_source import DataSourceError

    class AlwaysFailsSource(DataSource):
        name = "FAKE_FAILING_YAHOO"
        default_ttl_seconds = 3600

        def fetch(self, **kwargs):
            raise DataSourceError("simulated network failure")

    manager = DataIntegrityManager(min_quality_threshold=50.0)
    manager.register("PRICE_HISTORY_AAPL", primary=AlwaysFailsSource())
    manager.register("PRICE_HISTORY_MSFT", primary=AlwaysFailsSource())

    cycle_module._print_market_breadth(manager)
    output = capsys.readouterr().out
    assert "0 of 2 large-cap tickers usable" in output
