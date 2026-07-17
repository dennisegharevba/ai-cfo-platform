from unittest.mock import patch, MagicMock

import pytest

from connectors.sec_edgar_connector import SecEdgarConnector
from core.data_source import DataSourceError


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _companyconcept_payload(entries):
    return {"units": {"USD/shares": entries}}


def test_fetch_filters_to_10q_10k_and_sorts_newest_first():
    entries = [
        {"val": 1.50, "end": "2026-03-31", "form": "10-Q"},
        {"val": 1.20, "end": "2025-12-31", "form": "10-K"},
        {"val": 999, "end": "2026-01-01", "form": "8-K"},  # should be excluded
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    assert payload["latest_value"] == 1.50
    assert payload["latest_date"] == "2026-03-31"
    assert len(payload["history"]) == 2  # 8-K excluded
    assert provider_ts.year == 2026 and provider_ts.month == 3


def test_cik_is_zero_padded():
    connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
    assert connector.cik == "0000320193"


def test_missing_user_agent_raises_before_any_request():
    connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="")
    with pytest.raises(DataSourceError):
        connector.fetch()


def test_no_matching_filings_raises():
    entries = [{"val": 999, "end": "2026-01-01", "form": "8-K"}]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_empty_units_raises():
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response({"units": {}})):
        connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_validate_shape():
    connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
    assert connector.validate_shape({"latest_value": 1.5, "history": [{"value": 1.5}]}) is True
    assert connector.validate_shape({"latest_value": None, "history": []}) is False
    assert connector.validate_shape({"latest_value": 1.5, "history": []}) is False
