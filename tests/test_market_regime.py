from datetime import date

from agents.market_regime import (
    classify_regime, regime_adjusted_weight, MarketRegime,
)


def test_normal_month_with_no_fomc_dates_is_normal():
    result = classify_regime(date(2026, 2, 15), fomc_meeting_dates=[])
    assert result == {MarketRegime.NORMAL}


def test_earnings_season_month_detected():
    result = classify_regime(date(2026, 1, 20), fomc_meeting_dates=[])
    assert MarketRegime.EARNINGS_SEASON in result
    assert MarketRegime.NORMAL not in result


def test_non_earnings_month_not_flagged():
    result = classify_regime(date(2026, 2, 15), fomc_meeting_dates=[])
    assert MarketRegime.EARNINGS_SEASON not in result


def test_fomc_week_detected_within_window():
    meeting = date(2026, 3, 18)
    # 2 days before -> within the 3-day-before window
    result = classify_regime(date(2026, 3, 16), fomc_meeting_dates=[meeting])
    assert MarketRegime.FOMC_WEEK in result


def test_fomc_week_not_detected_outside_window():
    meeting = date(2026, 3, 18)
    result = classify_regime(date(2026, 3, 1), fomc_meeting_dates=[meeting])
    assert MarketRegime.FOMC_WEEK not in result


def test_fomc_and_earnings_season_can_both_be_active():
    meeting = date(2026, 1, 28)
    result = classify_regime(date(2026, 1, 28), fomc_meeting_dates=[meeting])
    assert MarketRegime.FOMC_WEEK in result
    assert MarketRegime.EARNINGS_SEASON in result


def test_empty_fomc_list_never_triggers_fomc_week():
    # Honest behavior for unconfigured data — never fabricates a meeting date.
    result = classify_regime(date(2026, 2, 15), fomc_meeting_dates=[])
    assert MarketRegime.FOMC_WEEK not in result


def test_none_fomc_dates_handled_same_as_empty_list():
    result = classify_regime(date(2026, 2, 15), fomc_meeting_dates=None)
    assert MarketRegime.FOMC_WEEK not in result


# --- regime_adjusted_weight ---

def test_fomc_week_boosts_macro_weight():
    result = regime_adjusted_weight(1.0, "Macroeconomic", {MarketRegime.FOMC_WEEK})
    assert result == 1.4


def test_normal_regime_leaves_weight_unchanged():
    result = regime_adjusted_weight(1.0, "Macroeconomic", {MarketRegime.NORMAL})
    assert result == 1.0


def test_unlisted_category_unaffected_by_any_regime():
    result = regime_adjusted_weight(1.0, "Some Unlisted Category", {MarketRegime.FOMC_WEEK, MarketRegime.EARNINGS_SEASON})
    assert result == 1.0


def test_multiple_active_regimes_multiply():
    # Both FOMC week and earnings season active; category only boosted by FOMC
    result = regime_adjusted_weight(1.0, "Macroeconomic", {MarketRegime.FOMC_WEEK, MarketRegime.EARNINGS_SEASON})
    assert result == 1.4  # earnings season multiplier for Macro is 1.0 (unlisted), so 1.4 * 1.0


def test_earnings_season_boosts_equity_fundamentals():
    result = regime_adjusted_weight(1.0, "Equity Fundamentals", {MarketRegime.EARNINGS_SEASON})
    assert result == 1.3
