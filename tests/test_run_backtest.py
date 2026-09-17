"""
Tests for scripts/run_backtest.py.

_fetch_price_history is the piece worth testing directly: it's a real,
isolated function with a clear contract, and it's exactly where a real
bug was caught via live testing (see the regression test below).
"""

import sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import _fetch_price_history, _resolve_price_ticker, _needs_fred_pacing, main
from core.data_source import DataSourceError


def _mock_payload(history):
    return ({"ticker": "TEST", "latest_close": history[0]["close"] if history else None,
             "latest_date": history[0]["date"] if history else None, "history": history}, datetime.now(timezone.utc))


def test_fetch_price_history_parses_the_real_isoformat_with_time_component():
    """
    Regression test for a real bug caught via live testing: this
    platform's own connectors/yahoo_history_connector.py builds its
    "date" field from a pandas Timestamp's .isoformat(), which includes a
    time component (e.g. "2026-08-05T00:00:00") — NOT a bare date string.
    An earlier version of _fetch_price_history parsed with
    strptime(row["date"], "%Y-%m-%d"), which raised ValueError on every
    single row, silently swallowed by a broad except clause — producing
    "0 daily closes" with no error message at all, only caught by
    actually running the script live against a real ticker.
    """
    history = [
        {"date": "2026-08-05T00:00:00", "close": 450.5, "high": 452.0, "low": 448.0},
        {"date": "2026-08-04T00:00:00", "close": 448.0, "high": 450.0, "low": 446.0},
    ]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.return_value = _mock_payload(history)
        result = _fetch_price_history("SPY")

    assert len(result) == 2  # NOT zero — the exact bug this test guards against
    assert result[0][1] == 448.0  # sorted oldest-first
    assert result[1][1] == 450.5


def test_fetch_price_history_handles_timezone_aware_isoformat():
    """pandas Timestamps can also produce a timezone-offset suffix
    (e.g. "-04:00") depending on the index's tz-awareness — proven
    separately from the bare case above, since this is a genuinely
    different string shape datetime.fromisoformat() needs to handle."""
    history = [{"date": "2026-08-05T00:00:00-04:00", "close": 450.5, "high": 452.0, "low": 448.0}]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.return_value = _mock_payload(history)
        result = _fetch_price_history("SPY")
    assert len(result) == 1


def test_fetch_price_history_skips_malformed_rows_without_crashing():
    history = [
        {"date": "2026-08-05T00:00:00", "close": 450.5},
        {"date": "not-a-date-at-all", "close": 100.0},
        {"no_date_field": True, "close": 100.0},
    ]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.return_value = _mock_payload(history)
        result = _fetch_price_history("SPY")
    assert len(result) == 1


def test_fetch_price_history_retries_and_recovers_from_a_transient_failure():
    """
    THE core regression test for a real, repeated live finding: Yahoo
    intermittently fails on large, genuinely-listed companies (Meta,
    Starbucks, Synopsys all failed as "possibly delisted" on real runs,
    none of them are actually delisted) — and which ticker fails is
    inconsistent run to run, not tied to scan position or request rate.
    A transient failure that succeeds on retry must return real data, not
    propagate the first failure.
    """
    good_history = [{"date": "2026-08-05T00:00:00", "close": 450.5}]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.side_effect = [
            DataSourceError("Yahoo Finance returned no history for SPY"),  # first attempt fails
            _mock_payload(good_history),  # retry succeeds
        ]
        result = _fetch_price_history("SPY", max_retries=2, retry_delay=0)
    assert len(result) == 1
    assert result[0][1] == 450.5


def test_fetch_price_history_raises_the_real_error_after_exhausting_retries():
    """A ticker that never recovers must still surface the real error —
    not swallow it into an empty result, which the calling scripts (that
    print "fetch failed — {exc}") rely on to report honestly which
    specific ticker failed and why."""
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.side_effect = DataSourceError("Yahoo Finance returned no history for XYZ")
        try:
            _fetch_price_history("XYZ", max_retries=2, retry_delay=0)
            assert False, "expected DataSourceError to be raised"
        except DataSourceError as exc:
            assert "XYZ" in str(exc)


def test_fetch_price_history_retries_exactly_max_retries_plus_one_attempts_total():
    """max_retries=2 means 3 total attempts (1 initial + 2 retries) —
    proven directly by counting calls, not just checking the outcome."""
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.side_effect = DataSourceError("still failing")
        try:
            _fetch_price_history("XYZ", max_retries=2, retry_delay=0)
        except DataSourceError:
            pass
    assert MockConnector.call_count == 3


def test_fetch_price_history_succeeds_immediately_without_retry_does_not_sleep(monkeypatch):
    """The common case (no failure at all) must not incur any retry
    delay — proven by asserting time.sleep is never called."""
    sleep_calls = []
    monkeypatch.setattr("scripts.run_backtest.time.sleep", lambda s: sleep_calls.append(s))
    history = [{"date": "2026-08-05T00:00:00", "close": 450.5}]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.return_value = _mock_payload(history)
        _fetch_price_history("SPY")
    assert sleep_calls == []


def test_fetch_price_and_volume_history_returns_real_volume():
    from scripts.run_backtest import _fetch_price_and_volume_history
    history = [
        {"date": "2026-08-05T00:00:00", "close": 450.5, "volume": 2_000_000.0},
        {"date": "2026-08-04T00:00:00", "close": 448.0, "volume": 1_500_000.0},
    ]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.return_value = _mock_payload(history)
        result = _fetch_price_and_volume_history("SPY")
    assert len(result) == 2
    assert result[0][2] == 1_500_000.0  # oldest first, volume is the 3rd element
    assert result[1][2] == 2_000_000.0


def test_fetch_price_and_volume_history_defaults_missing_volume_to_zero():
    from scripts.run_backtest import _fetch_price_and_volume_history
    history = [{"date": "2026-08-05T00:00:00", "close": 450.5}]  # no volume key at all
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.return_value = _mock_payload(history)
        result = _fetch_price_and_volume_history("EURUSD=X")
    assert result[0][2] == 0.0


def test_fetch_price_and_volume_history_shares_the_same_retry_logic():
    """Proves the refactor genuinely shares retry logic rather than
    duplicating it with different behavior — a transient failure must
    recover here exactly the same way it does for _fetch_price_history()."""
    from scripts.run_backtest import _fetch_price_and_volume_history
    good_history = [{"date": "2026-08-05T00:00:00", "close": 450.5, "volume": 1_000_000.0}]
    with patch("scripts.run_backtest.YahooHistoryConnector") as MockConnector:
        MockConnector.return_value.fetch.side_effect = [
            DataSourceError("transient failure"),
            _mock_payload(good_history),
        ]
        result = _fetch_price_and_volume_history("SPY", max_retries=2, retry_delay=0)
    assert len(result) == 1
    assert result[0][2] == 1_000_000.0


def test_resolve_price_ticker_uses_explicit_override_first():
    assert _resolve_price_ticker("Gold", explicit_ticker="XAUUSD=X") == "XAUUSD=X"


def test_resolve_price_ticker_auto_resolves_known_commodity_names():
    assert _resolve_price_ticker("Gold") == "GC=F"


def test_resolve_price_ticker_falls_back_to_asset_itself_when_unmapped():
    assert _resolve_price_ticker("SPY") == "SPY"


# --- rate-limit pacing ---

def test_needs_fred_pacing_false_for_seasonality():
    assert _needs_fred_pacing("seasonality") is False


def test_needs_fred_pacing_true_for_every_fred_based_signal():
    for signal in ("vix", "real_yield", "treasury_yield", "fed_policy", "CPI (Headline, YoY)", "GDP"):
        assert _needs_fred_pacing(signal) is True


def test_main_paces_requests_for_fred_based_signals(monkeypatch, capsys):
    """
    Regression test for a real issue caught via live use: the same
    command returned FEWER usable signal readings on a second run than
    the first (240 -> 220 of 261 dates), consistent with FRED's rate
    limit being hit partway through an unpaced run. Proven directly here
    that time.sleep() is genuinely invoked once per gap between test
    dates when a FRED-based signal is selected, using a fast fake delay
    so the test itself stays fast.
    """
    import scripts.run_backtest as rb_module

    monkeypatch.setattr(rb_module, "FRED_API_KEY", "FAKE_KEY_FOR_TEST")
    monkeypatch.setattr(rb_module, "SIGNAL_FUNCTIONS", {**rb_module.SIGNAL_FUNCTIONS, "vix": lambda d, asset: 10.0})
    monkeypatch.setattr(rb_module, "_fetch_price_history", lambda ticker: [
        (rb_module.date(2024, 1, 1), 100.0), (rb_module.date(2024, 3, 1), 105.0),
    ])
    sleep_calls = []
    monkeypatch.setattr(rb_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        "sys.argv",
        ["run_backtest.py", "--signal", "vix", "--asset", "SPY",
         "--start", "2024-01-01", "--end", "2024-02-01", "--step-days", "15", "--request-delay", "0.42"],
    )

    main()

    # 3 test dates (Jan 1, Jan 16, Jan 31) -> 2 gaps between them, each paced.
    assert len(sleep_calls) == 2
    assert all(delay == 0.42 for delay in sleep_calls)


def test_main_does_not_pace_seasonality(monkeypatch):
    """The exact same date-loop structure, but seasonality makes no FRED
    requests at all — no sleep should ever be called."""
    import scripts.run_backtest as rb_module

    monkeypatch.setattr(rb_module, "_fetch_price_history", lambda ticker: [
        (rb_module.date(2024, 1, 1), 100.0), (rb_module.date(2024, 3, 1), 105.0),
    ])
    sleep_calls = []
    monkeypatch.setattr(rb_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        "sys.argv",
        ["run_backtest.py", "--signal", "seasonality", "--asset", "Gold",
         "--start", "2024-01-01", "--end", "2024-02-01", "--step-days", "15"],
    )

    main()

    assert sleep_calls == []
