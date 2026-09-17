from agents.institutional_market_regime import (
    score_fed_policy, score_real_yield, score_treasury_yield, score_vix, vix_warning,
    combine_regime_scores, build_market_impact, build_regime_reasoning,
    InstitutionalMarketRegime,
)
from models.report import Bias


# --- score_fed_policy ---

def test_fed_policy_none_trend_returns_none():
    assert score_fed_policy(None) is None


def test_fed_policy_base_score_passthrough_with_no_overlays():
    assert score_fed_policy(60.0) == 60.0


def test_fed_policy_dovish_tone_boosts_score():
    result = score_fed_policy(20.0, fed_tone="dovish")
    assert result == 35.0  # 20 + 15


def test_fed_policy_very_hawkish_tone_reduces_score():
    result = score_fed_policy(20.0, fed_tone="very_hawkish")
    assert result == -10.0  # 20 - 30


def test_fed_policy_surprise_cut_is_bullish_adjustment():
    result = score_fed_policy(0.0, expected_decision="hold", actual_decision="cut", surprise_magnitude="large")
    assert result == 20.0


def test_fed_policy_surprise_hike_is_bearish_adjustment():
    result = score_fed_policy(0.0, expected_decision="hold", actual_decision="hike", surprise_magnitude="large")
    assert result == -20.0


def test_fed_policy_no_surprise_when_expected_matches_actual():
    result = score_fed_policy(0.0, expected_decision="hold", actual_decision="hold", surprise_magnitude="major")
    assert result == 0.0


def test_fed_policy_surprise_ignored_without_magnitude():
    # expected/actual supplied but no magnitude -> no adjustment applied
    result = score_fed_policy(10.0, expected_decision="hold", actual_decision="hike")
    assert result == 10.0


def test_fed_policy_clamped_to_100():
    result = score_fed_policy(90.0, fed_tone="very_dovish")
    assert result == 100.0


def test_fed_policy_clamped_to_negative_100():
    result = score_fed_policy(-90.0, fed_tone="very_hawkish")
    assert result == -100.0


# --- score_real_yield ---

def test_real_yield_strongly_falling():
    assert score_real_yield(-20.0) == 20.0


def test_real_yield_moderately_falling():
    assert score_real_yield(-8.0) == 10.0


def test_real_yield_neutral_band():
    assert score_real_yield(0.0) == 0.0
    assert score_real_yield(3.0) == 0.0
    assert score_real_yield(-3.0) == 0.0


def test_real_yield_moderately_rising():
    assert score_real_yield(8.0) == -10.0


def test_real_yield_strongly_rising():
    assert score_real_yield(20.0) == -20.0


def test_real_yield_none_returns_none():
    assert score_real_yield(None) is None


# --- score_treasury_yield ---

def test_treasury_yield_sharp_rise():
    assert score_treasury_yield(25.0) == -15.0


def test_treasury_yield_rising_not_sharp():
    assert score_treasury_yield(5.0) == -8.0


def test_treasury_yield_stable():
    assert score_treasury_yield(0.5) == 0.0
    assert score_treasury_yield(-0.5) == 0.0


def test_treasury_yield_falling():
    assert score_treasury_yield(-5.0) == 8.0


def test_treasury_yield_none_returns_none():
    assert score_treasury_yield(None) is None


# --- score_vix ---

def test_vix_risk_on_below_15():
    assert score_vix(12.0) == 20.0


def test_vix_mild_bullish_15_to_20():
    assert score_vix(17.0) == 10.0


def test_vix_neutral_20_to_25():
    assert score_vix(22.0) == 0.0


def test_vix_risk_off_warning_25_to_30():
    assert score_vix(27.0) == -20.0


def test_vix_high_risk_30_to_35():
    assert score_vix(32.0) == -40.0


def test_vix_extreme_above_35():
    assert score_vix(40.0) == -100.0


def test_vix_none_returns_none():
    assert score_vix(None) is None


def test_vix_warning_only_above_35():
    assert vix_warning(40.0) == "Extreme volatility regime. Long equity setups should be avoided."
    assert vix_warning(34.9) is None
    assert vix_warning(None) is None


# --- combine_regime_scores ---

def test_combine_all_components_bullish():
    result = combine_regime_scores(
        macro_score=50.0, fed_policy_score=50.0, real_yield_score=50.0,
        treasury_yield_score=50.0, vix_score=50.0,
    )
    assert result.combined_score == 50.0
    assert result.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert result.confidence == 100.0  # full coverage


def test_combine_respects_weights():
    # Only macro (40%) is strongly bullish; everything else strongly bearish.
    # Macro's weight should visibly pull the combined score up from what an
    # unweighted average would give.
    result = combine_regime_scores(
        macro_score=100.0, fed_policy_score=-100.0, real_yield_score=-100.0,
        treasury_yield_score=-100.0, vix_score=-100.0,
    )
    unweighted_avg = (100.0 - 100.0 - 100.0 - 100.0 - 100.0) / 5  # -60
    assert result.combined_score > unweighted_avg


def test_combine_missing_components_renormalizes_over_whats_available():
    only_macro = combine_regime_scores(
        macro_score=80.0, fed_policy_score=None, real_yield_score=None,
        treasury_yield_score=None, vix_score=None,
    )
    assert only_macro.combined_score == 80.0  # 100% of available weight is macro, at 80
    assert only_macro.confidence == 40.0  # only 40% of intended weight was covered


def test_combine_all_missing_returns_neutral_zero_confidence():
    result = combine_regime_scores(None, None, None, None, None)
    assert result.combined_score == 0.0
    assert result.bias == Bias.NEUTRAL
    assert result.confidence == 0.0


def test_combine_carries_vix_warning_through():
    result = combine_regime_scores(50.0, 50.0, 50.0, 50.0, -100.0, vix_level=40.0)
    assert result.vix_warning_message is not None


# --- InstitutionalMarketRegime display helpers ---

def test_display_score_converts_internal_to_0_100_scale():
    regime = InstitutionalMarketRegime(combined_score=0.0)
    assert regime.display_score() == 50.0
    regime2 = InstitutionalMarketRegime(combined_score=100.0)
    assert regime2.display_score() == 100.0
    regime3 = InstitutionalMarketRegime(combined_score=-100.0)
    assert regime3.display_score() == 0.0


def test_display_band_matches_spec_bands():
    assert InstitutionalMarketRegime(combined_score=100.0).display_band() == "Strong Bullish"
    assert InstitutionalMarketRegime(combined_score=60.0).display_band() == "Bullish"
    assert InstitutionalMarketRegime(combined_score=30.0).display_band() == "Moderately Bullish"
    assert InstitutionalMarketRegime(combined_score=0.0).display_band() == "Neutral"
    assert InstitutionalMarketRegime(combined_score=-30.0).display_band() == "Moderately Bearish"
    assert InstitutionalMarketRegime(combined_score=-60.0).display_band() == "Bearish"
    assert InstitutionalMarketRegime(combined_score=-100.0).display_band() == "Strong Bearish"


# --- build_market_impact ---

def test_market_impact_bullish_rate_environment():
    impact = build_market_impact(fed_policy_score=50.0, real_yield_score=50.0, treasury_yield_score=50.0)
    assert impact["Gold"] == "Bullish"
    assert impact["Silver"] == "Bullish"
    assert impact["NASDAQ100"] == "Bullish"
    assert impact["US Dollar"] == "Bearish"   # opposite direction
    assert impact["Treasury Bonds"] == "Bullish"


def test_market_impact_bearish_rate_environment():
    impact = build_market_impact(fed_policy_score=-50.0, real_yield_score=-50.0, treasury_yield_score=-50.0)
    assert impact["Gold"] == "Bearish"
    assert impact["US Dollar"] == "Bullish"


def test_market_impact_all_none_is_neutral():
    impact = build_market_impact(None, None, None)
    assert all(v == "Neutral" for v in impact.values())


# --- build_regime_reasoning ---

def test_reasoning_mentions_all_available_components():
    regime = combine_regime_scores(50.0, 50.0, 50.0, 50.0, 50.0)
    reasoning = build_regime_reasoning(regime)
    assert "Macro" in reasoning
    assert "Federal Reserve" in reasoning
    assert "Real yields" in reasoning
    assert "Treasury yields" in reasoning
    assert "VIX" in reasoning


def test_reasoning_includes_vix_warning_when_extreme():
    regime = combine_regime_scores(50.0, 50.0, 50.0, 50.0, -100.0, vix_level=40.0)
    reasoning = build_regime_reasoning(regime)
    assert "Extreme volatility regime" in reasoning


def test_reasoning_handles_all_missing_gracefully():
    regime = combine_regime_scores(None, None, None, None, None)
    reasoning = build_regime_reasoning(regime)
    assert "Insufficient data" in reasoning
