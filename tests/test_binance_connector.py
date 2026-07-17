from unittest.mock import patch, MagicMock

import pytest

from connectors.binance_connector import BinanceFuturesConnector
from core.data_source import DataSourceError


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _oi_rows_oldest_first(values):
    return [{"symbol": "BTCUSDT", "sumOpenInterest": str(v), "timestamp": 1700000000000 + i * 86400000}
            for i, v in enumerate(values)]


def _funding_payload(rate, time_ms=1700000000000):
    return {"symbol": "BTCUSDT", "markPrice": "60000", "lastFundingRate": str(rate), "time": time_ms}


def test_fetch_combines_oi_history_and_funding_rate():
    oi_rows = _oi_rows_oldest_first([1000, 1100, 1200])  # oldest first, as Binance returns it
    with patch("connectors.binance_connector.requests.get") as mock_get:
        mock_get.side_effect = [_mock_response(oi_rows), _mock_response(_funding_payload(0.0003))]
        connector = BinanceFuturesConnector("btcusdt", history_limit=3)
        payload, provider_ts = connector.fetch()

    assert payload["symbol"] == "BTCUSDT"  # uppercased
    assert payload["latest_funding_rate"] == 0.0003
    assert payload["latest_open_interest"] == "1200"  # newest-first after reversal
    assert payload["history"][0]["open_interest"] == "1200"
    assert payload["history"][-1]["open_interest"] == "1000"
    assert provider_ts is not None


def test_empty_oi_history_raises():
    with patch("connectors.binance_connector.requests.get", return_value=_mock_response([])):
        connector = BinanceFuturesConnector("BTCUSDT")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_missing_funding_rate_raises():
    oi_rows = _oi_rows_oldest_first([1000, 1100])
    with patch("connectors.binance_connector.requests.get") as mock_get:
        mock_get.side_effect = [_mock_response(oi_rows), _mock_response({"symbol": "BTCUSDT"})]
        connector = BinanceFuturesConnector("BTCUSDT")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_history_limit_minimum_enforced():
    connector = BinanceFuturesConnector("BTCUSDT", history_limit=1)
    assert connector.history_limit == 2


def test_validate_shape():
    connector = BinanceFuturesConnector("BTCUSDT")
    assert connector.validate_shape({"latest_funding_rate": 0.0001, "history": [{"open_interest": "1"}]}) is True
    assert connector.validate_shape({"latest_funding_rate": None, "history": []}) is False
    assert connector.validate_shape({"latest_funding_rate": 0.0001, "history": []}) is False
