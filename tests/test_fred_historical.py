from unittest.mock import patch, MagicMock
from datetime import date

from connectors.fred_historical import fetch_point_in_time_value, fetch_point_in_time_history, NON_REVISED_SERIES


def _mock_response(observations):
    resp = MagicMock()
    resp.json.return_value = {"observations": observations}
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_returns_value_and_observation_date():
    obs = [{"date": "2020-05-01", "value": "0.13"}]
    with patch("connectors.fred_historical.requests.get", return_value=_mock_response(obs)) as mock_get:
        result = fetch_point_in_time_value("FEDFUNDS", api_key="TEST_KEY", as_of_date=date(2020, 6, 1))

    assert result == (0.13, date(2020, 5, 1))
    # Confirm the vintage-query parameters were actually sent — the whole
    # point of this module — not just that SOME request was made.
    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["realtime_start"] == "2020-06-01"
    assert call_params["realtime_end"] == "2020-06-01"


def test_missing_api_key_returns_none_never_raises():
    result = fetch_point_in_time_value("CPIAUCSL", api_key="", as_of_date=date(2020, 1, 1))
    assert result is None


def test_no_observations_returns_none():
    with patch("connectors.fred_historical.requests.get", return_value=_mock_response([])):
        result = fetch_point_in_time_value("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 1, 1))
    assert result is None


def test_network_error_returns_none_never_raises():
    import requests

    with patch("connectors.fred_historical.requests.get", side_effect=requests.RequestException("boom")):
        result = fetch_point_in_time_value("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 1, 1))
    assert result is None


def test_malformed_observation_returns_none():
    obs = [{"date": "2020-05-01", "value": "."}]  # FRED uses "." for missing values
    with patch("connectors.fred_historical.requests.get", return_value=_mock_response(obs)):
        result = fetch_point_in_time_value("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 6, 1))
    assert result is None


def test_non_revised_series_list_contains_expected_market_series():
    assert "FEDFUNDS" in NON_REVISED_SERIES
    assert "VIXCLS" in NON_REVISED_SERIES
    assert "DFII10" in NON_REVISED_SERIES
    # DFEDTARU/DFEDTARL (Fed Funds Target Range, upper/lower limit) — the
    # daily series agents.chief_macro_officer / agents.backtest_signals
    # switched the Fed Funds factor to (2026-09-17), away from FEDFUNDS's
    # monthly average. Set by the FOMC directly and never revised after
    # the fact, same category as VIXCLS/DFII10 above.
    assert "DFEDTARU" in NON_REVISED_SERIES
    assert "DFEDTARL" in NON_REVISED_SERIES
    # A genuinely revised survey series should NOT be in this list.
    assert "CPIAUCSL" not in NON_REVISED_SERIES


# --- fetch_point_in_time_history ---

def test_history_returns_newest_first_list_matching_live_payload_shape():
    obs = [
        {"date": "2020-05-01", "value": "260.5"},
        {"date": "2020-04-01", "value": "259.8"},
        {"date": "2020-03-01", "value": "258.1"},
    ]
    with patch("connectors.fred_historical.requests.get", return_value=_mock_response(obs)) as mock_get:
        history = fetch_point_in_time_history("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 6, 1), limit=5)

    assert history == [
        {"date": "2020-05-01", "value": "260.5"},
        {"date": "2020-04-01", "value": "259.8"},
        {"date": "2020-03-01", "value": "258.1"},
    ]
    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["realtime_start"] == "2020-06-01"
    assert call_params["realtime_end"] == "2020-06-01"
    assert call_params["limit"] == 5


def test_history_missing_api_key_returns_none():
    assert fetch_point_in_time_history("CPIAUCSL", api_key="", as_of_date=date(2020, 1, 1)) is None


def test_history_no_observations_returns_none():
    with patch("connectors.fred_historical.requests.get", return_value=_mock_response([])):
        result = fetch_point_in_time_history("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 1, 1))
    assert result is None


def test_history_network_error_returns_none():
    import requests

    with patch("connectors.fred_historical.requests.get", side_effect=requests.RequestException("boom")):
        result = fetch_point_in_time_history("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 1, 1))
    assert result is None


def test_history_skips_malformed_rows_but_keeps_valid_ones():
    obs = [{"date": "2020-05-01", "value": "260.5"}, {"no_date_field": True}, {"date": "2020-03-01", "value": "258.1"}]
    with patch("connectors.fred_historical.requests.get", return_value=_mock_response(obs)):
        history = fetch_point_in_time_history("CPIAUCSL", api_key="TEST_KEY", as_of_date=date(2020, 6, 1))
    assert len(history) == 2
