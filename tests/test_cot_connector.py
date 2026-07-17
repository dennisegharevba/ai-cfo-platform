from unittest.mock import patch, MagicMock

import pytest

from connectors.cot_connector import CotConnector
from core.data_source import DataSourceError


def _fake_row(date, noncomm_long, noncomm_short, oi):
    return {
        "report_date_as_yyyy_mm_dd": date,
        "noncomm_positions_long_all": str(noncomm_long),
        "noncomm_positions_short_all": str(noncomm_short),
        "comm_positions_long_all": "1000",
        "comm_positions_short_all": "900",
        "open_interest_all": str(oi),
    }


def _mock_response(rows):
    resp = MagicMock()
    resp.json.return_value = rows
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_builds_history_newest_first_and_top_level_matches_latest():
    rows = [
        _fake_row("2026-07-08T00:00:00.000", 100000, 80000, 500000),
        _fake_row("2026-07-01T00:00:00.000", 95000, 82000, 490000),
    ]
    with patch("connectors.cot_connector.requests.get", return_value=_mock_response(rows)):
        connector = CotConnector("GOLD - COMMODITY EXCHANGE INC.", weeks_history=2)
        payload, provider_ts = connector.fetch()

    assert payload["noncomm_long"] == "100000"
    assert payload["noncomm_short"] == "80000"
    assert payload["open_interest"] == "500000"
    assert len(payload["history"]) == 2
    assert payload["history"][0]["report_date"] == "2026-07-08T00:00:00.000"
    assert payload["history"][1]["report_date"] == "2026-07-01T00:00:00.000"
    assert provider_ts is not None
    assert provider_ts.year == 2026 and provider_ts.month == 7 and provider_ts.day == 8


def test_fetch_requests_the_configured_number_of_weeks():
    rows = [_fake_row(f"2026-0{i}-01T00:00:00.000", 100000, 80000, 500000) for i in range(1, 5)]
    with patch("connectors.cot_connector.requests.get", return_value=_mock_response(rows)) as mock_get:
        connector = CotConnector("GOLD - COMMODITY EXCHANGE INC.", weeks_history=4)
        connector.fetch()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["$limit"] == 4


def test_weeks_history_minimum_enforced():
    connector = CotConnector("GOLD - COMMODITY EXCHANGE INC.", weeks_history=1)
    assert connector.weeks_history == 2  # floored to minimum useful value


def test_empty_rows_raises_data_source_error():
    with patch("connectors.cot_connector.requests.get", return_value=_mock_response([])):
        connector = CotConnector("NONEXISTENT MARKET")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_validate_shape_requires_nonempty_history():
    connector = CotConnector("GOLD - COMMODITY EXCHANGE INC.")
    good_payload = {
        "noncomm_long": "100", "noncomm_short": "80", "open_interest": "500",
        "history": [{"report_date": "2026-07-08"}],
    }
    bad_payload_no_history = {
        "noncomm_long": "100", "noncomm_short": "80", "open_interest": "500",
        "history": [],
    }
    assert connector.validate_shape(good_payload) is True
    assert connector.validate_shape(bad_payload_no_history) is False
