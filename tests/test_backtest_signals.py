from datetime import date
from unittest.mock import patch

from agents.backtest_signals import (
    seasonality_signal, vix_signal, real_yield_signal, treasury_yield_signal, fed_policy_signal,
    macro_factor_signal, MACRO_FACTOR_NAMES,
)


def test_seasonality_signal_matches_the_real_scoring_function():
    result = seasonality_signal("Gold", date(2026, 9, 15))
    assert result == 25.0  # matches agents/seasonality_scoring.py's documented September Gold score


def test_seasonality_signal_none_for_unconfigured_asset():
    assert seasonality_signal("Some Unlisted Asset", date(2026, 9, 15)) is None


def test_vix_signal_uses_point_in_time_fetch():
    with patch("agents.backtest_signals.fetch_point_in_time_value", return_value=(12.0, date(2020, 6, 1))) as mock_fetch:
        result = vix_signal(date(2020, 6, 1), "TEST_KEY")
    mock_fetch.assert_called_once_with("VIXCLS", "TEST_KEY", date(2020, 6, 1))
    assert result == 20.0  # score_vix(12.0) -> Risk-On band


def test_vix_signal_none_when_data_unavailable():
    with patch("agents.backtest_signals.fetch_point_in_time_value", return_value=None):
        assert vix_signal(date(2020, 6, 1), "TEST_KEY") is None


def test_real_yield_signal_computes_change_from_two_point_in_time_queries():
    def fake_fetch(series_id, api_key, as_of_date):
        if as_of_date == date(2020, 6, 1):
            return (1.0, as_of_date)  # current: 1.0%
        return (1.5, as_of_date)      # 30 days earlier: 1.5% -> falling 50bps

    with patch("agents.backtest_signals.fetch_point_in_time_value", side_effect=fake_fetch):
        result = real_yield_signal(date(2020, 6, 1), "TEST_KEY")
    assert result == 20.0  # score_real_yield(-50) -> a 50bps fall is well past the strongly-falling threshold (15bps)


def test_real_yield_signal_none_when_either_query_fails():
    def fake_fetch(series_id, api_key, as_of_date):
        return None if as_of_date == date(2020, 6, 1) else (1.5, as_of_date)

    with patch("agents.backtest_signals.fetch_point_in_time_value", side_effect=fake_fetch):
        assert real_yield_signal(date(2020, 6, 1), "TEST_KEY") is None


def test_treasury_yield_signal_computes_change_from_two_point_in_time_queries():
    def fake_fetch(series_id, api_key, as_of_date):
        if as_of_date == date(2020, 6, 1):
            return (4.5, as_of_date)  # current: 4.5%
        return (4.0, as_of_date)      # 7 days earlier: 4.0% -> rising 50bps

    with patch("agents.backtest_signals.fetch_point_in_time_value", side_effect=fake_fetch):
        result = treasury_yield_signal(date(2020, 6, 1), "TEST_KEY")
    assert result == -15.0  # score_treasury_yield(+50) -> a 50bps/week rise is well past the sharp-rise threshold (20bps)


def test_fed_policy_signal_computes_trend_from_two_point_in_time_queries():
    def fake_fetch(series_id, api_key, as_of_date):
        if as_of_date == date(2020, 6, 1):
            return (0.25, as_of_date)  # current: 0.25%
        return (1.50, as_of_date)      # 90 days earlier: 1.50% -> big cut

    with patch("agents.backtest_signals.fetch_point_in_time_value", side_effect=fake_fetch):
        result = fed_policy_signal(date(2020, 6, 1), "TEST_KEY")
    assert result is not None
    assert result > 0  # a large rate cut should score bullish


def test_fed_policy_signal_none_when_either_query_fails():
    def fake_fetch(series_id, api_key, as_of_date):
        return None if as_of_date == date(2020, 6, 1) else (1.5, as_of_date)

    with patch("agents.backtest_signals.fetch_point_in_time_value", side_effect=fake_fetch):
        assert fed_policy_signal(date(2020, 6, 1), "TEST_KEY") is None


# --- macro_factor_signal (all 16 Chief Macro Officer factors) ---

def test_macro_factor_names_has_all_16_factors():
    assert len(MACRO_FACTOR_NAMES) == 16
    assert "CPI (Headline, YoY)" in MACRO_FACTOR_NAMES
    assert "Initial Jobless Claims" in MACRO_FACTOR_NAMES
    assert "Federal Debt (Total Public Debt)" in MACRO_FACTOR_NAMES


def test_macro_factor_signal_unrecognized_name_returns_none():
    assert macro_factor_signal("Not A Real Factor", date(2020, 6, 1), "TEST_KEY") is None


def test_macro_factor_signal_none_when_history_fetch_fails():
    with patch("agents.backtest_signals.fetch_point_in_time_history", return_value=None):
        assert macro_factor_signal("CPI (Headline, YoY)", date(2020, 6, 1), "TEST_KEY") is None


def test_macro_factor_signal_falling_cpi_is_bullish():
    """CPI is lower_is_bullish=True — a declining price series should score positive."""
    falling_history = [
        {"date": "2020-05-01", "value": "256.0"},
        {"date": "2020-04-01", "value": "258.0"},
        {"date": "2020-03-01", "value": "260.0"},
        {"date": "2020-02-01", "value": "262.0"},
        {"date": "2020-01-01", "value": "264.0"},
    ]
    with patch("agents.backtest_signals.fetch_point_in_time_history", return_value=falling_history):
        result = macro_factor_signal("CPI (Headline, YoY)", date(2020, 6, 1), "TEST_KEY")
    assert result is not None
    assert result > 0


def test_macro_factor_signal_rising_gdp_is_bullish():
    """GDP is lower_is_bullish=False — a rising level series should score positive."""
    rising_history = [
        {"date": "2020-05-01", "value": "21500.0"},
        {"date": "2020-04-01", "value": "21400.0"},
        {"date": "2020-03-01", "value": "21300.0"},
        {"date": "2020-02-01", "value": "21200.0"},
        {"date": "2020-01-01", "value": "21100.0"},
    ]
    with patch("agents.backtest_signals.fetch_point_in_time_history", return_value=rising_history):
        result = macro_factor_signal("GDP", date(2020, 6, 1), "TEST_KEY")
    assert result is not None
    assert result > 0


def test_macro_factor_signal_uses_that_factors_own_calibrated_normalization():
    """
    Direct proof that macro_factor_signal() reads normalization_pct from
    chief_macro_officer._FACTOR_SPECS rather than a hardcoded/duplicated
    value: the SAME percent move should clamp for a tightly-banded factor
    (CPI, 5.0) but NOT clamp for a widely-banded one recalibrated after
    the live over-clamping finding (Initial Jobless Claims, 15.0) — see
    docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md.
    """
    # An 8% decline over the window — clamps at 5.0, doesn't clamp at 15.0.
    eight_pct_decline = [
        {"date": "2020-05-01", "value": "92.0"},
        {"date": "2020-04-01", "value": "94.0"},
        {"date": "2020-03-01", "value": "96.0"},
        {"date": "2020-02-01", "value": "98.0"},
        {"date": "2020-01-01", "value": "100.0"},
    ]
    with patch("agents.backtest_signals.fetch_point_in_time_history", return_value=eight_pct_decline):
        cpi_result = macro_factor_signal("CPI (Headline, YoY)", date(2020, 6, 1), "TEST_KEY")
        claims_result = macro_factor_signal("Initial Jobless Claims", date(2020, 6, 1), "TEST_KEY")

    assert abs(cpi_result) == 100.0
    assert abs(claims_result) < 100.0


def test_macro_factor_signal_respects_history_limit_parameter():
    with patch("agents.backtest_signals.fetch_point_in_time_history") as mock_fetch:
        mock_fetch.return_value = None
        macro_factor_signal("GDP", date(2020, 6, 1), "TEST_KEY", history_limit=8)
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs.get("limit") == 8 or mock_fetch.call_args.args[-1] == 8 or 8 in mock_fetch.call_args.args
