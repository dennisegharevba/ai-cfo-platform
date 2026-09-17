from unittest.mock import patch, MagicMock

import pytest

from connectors.eia_connector import EiaConnector
from core.data_source import DataSourceError


def _mock_response(rows):
    resp = MagicMock()
    resp.json.return_value = {"response": {"data": rows}}
    resp.raise_for_status.return_value = None
    return resp


def _row(period, value):
    return {"period": period, "value": value, "product": "EPC0", "duoarea": "NUS"}


def test_fetch_builds_history_and_sorts_newest_first():
    # Deliberately out of order to prove the connector sorts defensively
    rows = [_row("2026-06-01", 420.0), _row("2026-06-15", 410.0), _row("2026-05-15", 430.0)]
    with patch("connectors.eia_connector.requests.get", return_value=_mock_response(rows)):
        connector = EiaConnector(route="petroleum/stoc/wstk", facets={"product": ["EPC0"]}, api_key="TEST_KEY")
        payload, provider_ts = connector.fetch()

    assert payload["latest_value"] == 410.0
    assert payload["latest_date"] == "2026-06-15"
    assert payload["history"][0]["value"] == 410.0
    assert payload["history"][-1]["value"] == 430.0
    assert provider_ts is not None
    assert provider_ts.year == 2026 and provider_ts.month == 6 and provider_ts.day == 15


def test_missing_api_key_raises_before_any_request():
    connector = EiaConnector(route="petroleum/stoc/wstk", facets={}, api_key="")
    with pytest.raises(DataSourceError):
        connector.fetch()


def test_empty_rows_raises():
    with patch("connectors.eia_connector.requests.get", return_value=_mock_response([])):
        connector = EiaConnector(route="petroleum/stoc/wstk", facets={"product": ["EPC0"]}, api_key="TEST_KEY")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_rows_with_null_values_are_skipped():
    rows = [_row("2026-06-15", None), _row("2026-06-01", 420.0)]
    with patch("connectors.eia_connector.requests.get", return_value=_mock_response(rows)):
        connector = EiaConnector(route="petroleum/stoc/wstk", facets={"product": ["EPC0"]}, api_key="TEST_KEY")
        payload, _ = connector.fetch()
    assert payload["latest_value"] == 420.0
    assert len(payload["history"]) == 1


def test_all_null_values_raises():
    rows = [_row("2026-06-15", None), _row("2026-06-01", None)]
    with patch("connectors.eia_connector.requests.get", return_value=_mock_response(rows)):
        connector = EiaConnector(route="petroleum/stoc/wstk", facets={"product": ["EPC0"]}, api_key="TEST_KEY")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_facets_are_encoded_into_request_params():
    rows = [_row("2026-06-15", 420.0)]
    with patch("connectors.eia_connector.requests.get", return_value=_mock_response(rows)) as mock_get:
        connector = EiaConnector(
            route="petroleum/stoc/wstk", facets={"product": ["EPC0"], "duoarea": ["NUS"]}, api_key="TEST_KEY",
        )
        connector.fetch()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["facets[product][0]"] == "EPC0"
    assert kwargs["params"]["facets[duoarea][0]"] == "NUS"


def test_periods_history_minimum_enforced():
    connector = EiaConnector(route="x", facets={}, api_key="TEST_KEY", periods_history=1)
    assert connector.periods_history == 2


def test_validate_shape():
    connector = EiaConnector(route="x", facets={}, api_key="TEST_KEY")
    assert connector.validate_shape({"latest_value": 420.0, "history": [{"value": 420.0}]}) is True
    assert connector.validate_shape({"latest_value": None, "history": []}) is False
    assert connector.validate_shape({"latest_value": 420.0, "history": []}) is False
