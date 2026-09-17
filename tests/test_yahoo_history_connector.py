from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from connectors.yahoo_history_connector import YahooHistoryConnector
from core.data_source import DataSourceError


def _fake_history_df(closes, volumes=None):
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    data = {"Close": closes}
    if volumes is not None:
        data["Volume"] = volumes
    return pd.DataFrame(data, index=dates)


def test_fetch_parses_and_reverses_to_newest_first():
    df = _fake_history_df([100.0, 101.0, 102.0, 103.0, 104.0])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    with patch("yfinance.Ticker", return_value=fake_ticker):
        connector = YahooHistoryConnector("AAPL")
        payload, provider_ts = connector.fetch()

    assert payload["ticker"] == "AAPL"
    assert payload["latest_close"] == 104.0
    assert payload["history"][0]["close"] == 104.0   # newest first
    assert payload["history"][-1]["close"] == 100.0  # oldest last
    assert len(payload["history"]) == 5
    assert provider_ts is not None


def test_fetch_includes_real_volume_when_present():
    df = _fake_history_df([100.0, 101.0], volumes=[1_000_000, 2_000_000])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    with patch("yfinance.Ticker", return_value=fake_ticker):
        connector = YahooHistoryConnector("AAPL")
        payload, _ = connector.fetch()

    assert payload["history"][0]["volume"] == 2_000_000.0  # newest first
    assert payload["history"][-1]["volume"] == 1_000_000.0


def test_fetch_volume_falls_back_to_zero_when_column_missing():
    """No Volume column at all (some instruments) — must default to 0.0,
    not crash, and never fabricate a close-derived or guessed value."""
    df = _fake_history_df([100.0, 101.0])  # no volumes= passed
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    with patch("yfinance.Ticker", return_value=fake_ticker):
        connector = YahooHistoryConnector("EURUSD=X")
        payload, _ = connector.fetch()

    assert all(row["volume"] == 0.0 for row in payload["history"])


def test_fetch_volume_falls_back_to_zero_when_nan():
    """Some FX pairs report NaN volume via yfinance even when the column
    exists — must default to 0.0 (a clear 'not usable' signal for
    callers), never propagate a NaN into downstream scoring."""
    import math
    df = _fake_history_df([100.0, 101.0], volumes=[math.nan, math.nan])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    with patch("yfinance.Ticker", return_value=fake_ticker):
        connector = YahooHistoryConnector("EURUSD=X")
        payload, _ = connector.fetch()

    assert all(row["volume"] == 0.0 for row in payload["history"])


def test_empty_dataframe_raises():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame()

    with patch("yfinance.Ticker", return_value=fake_ticker):
        connector = YahooHistoryConnector("NOSUCHTICKER")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_validate_shape_requires_minimum_history_length():
    connector = YahooHistoryConnector("AAPL")
    short_history = [{"close": 100.0, "date": "2026-01-01"}] * 5
    long_history = [{"close": 100.0, "date": "2026-01-01"}] * 20
    assert connector.validate_shape({"latest_close": 100.0, "history": short_history}) is False
    assert connector.validate_shape({"latest_close": 100.0, "history": long_history}) is True


def test_validate_shape_requires_latest_close():
    connector = YahooHistoryConnector("AAPL")
    assert connector.validate_shape({"latest_close": None, "history": [{}] * 20}) is False
