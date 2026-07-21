from unittest.mock import patch, MagicMock

import pytest

from connectors.sec_ticker_lookup import SecTickerCikConnector, resolve_cik
from core.data_source import DataSourceError
from core.refresh_manager import DataIntegrityManager


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


SAMPLE_MAP = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
}


def test_fetch_parses_ticker_to_cik_map():
    with patch("connectors.sec_ticker_lookup.requests.get", return_value=_mock_response(SAMPLE_MAP)):
        connector = SecTickerCikConnector(user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    assert payload["ticker_to_cik"]["AAPL"] == "0000320193"
    assert payload["ticker_to_cik"]["MSFT"] == "0000789019"
    assert payload["count"] == 3
    assert provider_ts is not None


def test_missing_user_agent_raises_before_any_request():
    connector = SecTickerCikConnector(user_agent="")
    with pytest.raises(DataSourceError):
        connector.fetch()


def test_empty_map_raises():
    with patch("connectors.sec_ticker_lookup.requests.get", return_value=_mock_response({})):
        connector = SecTickerCikConnector(user_agent="Test test@example.com")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_validate_shape_requires_sanity_check_tickers():
    connector = SecTickerCikConnector(user_agent="Test test@example.com")
    assert connector.validate_shape({"ticker_to_cik": {"AAPL": "1", "MSFT": "2"}}) is True
    assert connector.validate_shape({"ticker_to_cik": {"SOMEOBSCURETICKER": "1"}}) is False
    assert connector.validate_shape({"ticker_to_cik": {}}) is False


def test_resolve_cik_returns_correct_value():
    with patch("connectors.sec_ticker_lookup.requests.get", return_value=_mock_response(SAMPLE_MAP)):
        manager = DataIntegrityManager(min_quality_threshold=50)
        cik = resolve_cik(manager, "AAPL", user_agent="Test test@example.com")
    assert cik == "0000320193"


def test_resolve_cik_case_insensitive():
    with patch("connectors.sec_ticker_lookup.requests.get", return_value=_mock_response(SAMPLE_MAP)):
        manager = DataIntegrityManager(min_quality_threshold=50)
        cik = resolve_cik(manager, "aapl", user_agent="Test test@example.com")
    assert cik == "0000320193"


def test_resolve_cik_unknown_ticker_returns_none():
    with patch("connectors.sec_ticker_lookup.requests.get", return_value=_mock_response(SAMPLE_MAP)):
        manager = DataIntegrityManager(min_quality_threshold=50)
        cik = resolve_cik(manager, "NOSUCHTICKER", user_agent="Test test@example.com")
    assert cik is None


def test_resolve_cik_reuses_cached_map_across_calls():
    with patch("connectors.sec_ticker_lookup.requests.get", return_value=_mock_response(SAMPLE_MAP)) as mock_get:
        manager = DataIntegrityManager(min_quality_threshold=50)
        resolve_cik(manager, "AAPL", user_agent="Test test@example.com")
        resolve_cik(manager, "MSFT", user_agent="Test test@example.com")
        resolve_cik(manager, "GOOGL", user_agent="Test test@example.com")
    assert mock_get.call_count == 1  # one fetch resolves every subsequent lookup


def test_resolve_cik_returns_none_when_source_unreachable():
    from core.data_source import DataSourceError as DSError

    class FailingConnector(SecTickerCikConnector):
        def fetch(self, **kwargs):
            raise DSError("simulated outage")

    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("SEC_TICKER_CIK_MAP", primary=FailingConnector(user_agent="Test test@example.com"))
    cik = resolve_cik(manager, "AAPL", user_agent="Test test@example.com")
    assert cik is None
