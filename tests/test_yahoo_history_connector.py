from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from connectors.yahoo_history_connector import YahooHistoryConnector
from core.data_source import DataSourceError


def _fake_history_df(closes):
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=dates)


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
