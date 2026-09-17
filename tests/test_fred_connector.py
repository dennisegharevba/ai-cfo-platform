from unittest.mock import patch, MagicMock

from connectors.fred_connector import FredConnector


def _mock_response(observations):
    resp = MagicMock()
    resp.json.return_value = {"observations": observations}
    resp.raise_for_status.return_value = None
    return resp


def test_default_limit_is_five():
    obs = [{"date": "2026-06-01", "value": "3.5"}]
    with patch("connectors.fred_connector.requests.get", return_value=_mock_response(obs)) as mock_get:
        FredConnector(series_id="CPIAUCSL", api_key="TEST_KEY").fetch()
    assert mock_get.call_args.kwargs["params"]["limit"] == 5


def test_limit_is_configurable_for_daily_series():
    """
    Needed for DFEDTARU (Federal Funds Target Range) — a DAILY series that
    repeats the same value every day between FOMC meetings. The default
    5-observation window (right for this platform's usual monthly/
    quarterly series) would almost always see 5 identical days and read as
    flat. See agents/chief_macro_officer.py's _FRED_SERIES_LIMIT_OVERRIDES.
    """
    obs = [{"date": "2026-06-01", "value": "3.5"}]
    with patch("connectors.fred_connector.requests.get", return_value=_mock_response(obs)) as mock_get:
        FredConnector(series_id="DFEDTARU", api_key="TEST_KEY", limit=90).fetch()
    assert mock_get.call_args.kwargs["params"]["limit"] == 90
