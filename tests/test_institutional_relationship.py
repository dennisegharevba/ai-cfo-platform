from agents.institutional_relationship import (
    AlignmentStatus, classify_alignment, apply_confidence_adjustment, describe_alignment,
    ExecutionReadiness, classify_execution_readiness, build_institutional_commentary,
)
from models.report import Bias, RiskLevel


# --- classify_alignment ---

def test_same_sign_is_full_alignment():
    assert classify_alignment(50.0, 30.0) == AlignmentStatus.FULL_ALIGNMENT
    assert classify_alignment(-50.0, -30.0) == AlignmentStatus.FULL_ALIGNMENT


def test_opposite_signs_small_magnitude_still_full_alignment():
    # Opposite signs, but both negligible -> not a meaningful conflict
    assert classify_alignment(5.0, -5.0) == AlignmentStatus.FULL_ALIGNMENT


def test_opposite_signs_moderate_magnitude_is_mild_divergence():
    assert classify_alignment(30.0, -30.0) == AlignmentStatus.MILD_DIVERGENCE


def test_opposite_signs_large_magnitude_is_strong_divergence():
    assert classify_alignment(80.0, -80.0) == AlignmentStatus.STRONG_DIVERGENCE


def test_either_score_none_returns_none():
    assert classify_alignment(None, 30.0) is None
    assert classify_alignment(30.0, None) is None
    assert classify_alignment(None, None) is None


def test_zero_vs_nonzero_is_full_alignment():
    # zero * anything = 0 >= 0 -> full alignment (no real conflict)
    assert classify_alignment(0.0, -40.0) == AlignmentStatus.FULL_ALIGNMENT


# --- apply_confidence_adjustment ---

def test_full_alignment_increases_confidence():
    result = apply_confidence_adjustment(60.0, AlignmentStatus.FULL_ALIGNMENT)
    assert result == 75.0


def test_mild_divergence_decreases_confidence():
    result = apply_confidence_adjustment(60.0, AlignmentStatus.MILD_DIVERGENCE)
    assert result == 50.0


def test_strong_divergence_decreases_confidence_more():
    result = apply_confidence_adjustment(60.0, AlignmentStatus.STRONG_DIVERGENCE)
    assert result == 35.0


def test_confidence_adjustment_clamped_to_100():
    result = apply_confidence_adjustment(95.0, AlignmentStatus.FULL_ALIGNMENT)
    assert result == 100.0


def test_confidence_adjustment_clamped_to_0():
    result = apply_confidence_adjustment(10.0, AlignmentStatus.STRONG_DIVERGENCE)
    assert result == 0.0


def test_none_status_is_a_no_op():
    assert apply_confidence_adjustment(55.0, None) == 55.0


# --- describe_alignment ---

def test_describe_full_alignment_has_no_risk():
    d = describe_alignment(AlignmentStatus.FULL_ALIGNMENT)
    assert "Institutional Alignment" in d["evidence"]
    assert d["risk"] is None
    assert d["catalyst"] is not None


def test_describe_mild_divergence_has_risk_not_catalyst():
    d = describe_alignment(AlignmentStatus.MILD_DIVERGENCE)
    assert "Institutional Divergence" in d["evidence"]
    assert d["risk"] is not None
    assert "diverg" in d["risk"].lower()
    assert d["catalyst"] is None


def test_describe_strong_divergence_mentions_no_trade():
    d = describe_alignment(AlignmentStatus.STRONG_DIVERGENCE)
    assert "High Institutional Uncertainty" in d["evidence"]
    assert "no trade" in d["risk"].lower()


# --- classify_execution_readiness ---

def test_neutral_bias_is_always_no_trade():
    result = classify_execution_readiness(Bias.NEUTRAL, 90.0, RiskLevel.LOW, True)
    assert result == ExecutionReadiness.NO_TRADE


def test_low_confidence_is_no_trade_regardless_of_bias():
    result = classify_execution_readiness(Bias.BULLISH, 20.0, RiskLevel.LOW, True)
    assert result == ExecutionReadiness.NO_TRADE


def test_high_risk_caps_readiness_below_high_conviction():
    result = classify_execution_readiness(Bias.BULLISH, 90.0, RiskLevel.HIGH, True)
    assert result == ExecutionReadiness.CONDITIONAL_OPPORTUNITY


def test_high_risk_with_low_confidence_is_no_trade():
    result = classify_execution_readiness(Bias.BULLISH, 40.0, RiskLevel.HIGH, True)
    assert result == ExecutionReadiness.NO_TRADE


def test_full_conditions_met_gives_high_conviction():
    result = classify_execution_readiness(Bias.BULLISH, 80.0, RiskLevel.MODERATE, True)
    assert result == ExecutionReadiness.HIGH_CONVICTION


def test_high_confidence_but_no_technical_confirmation_is_conditional_not_high_conviction():
    result = classify_execution_readiness(Bias.BULLISH, 80.0, RiskLevel.MODERATE, None)
    assert result == ExecutionReadiness.CONDITIONAL_OPPORTUNITY


def test_high_confidence_but_technical_disagrees_is_conditional_not_high_conviction():
    result = classify_execution_readiness(Bias.BULLISH, 80.0, RiskLevel.MODERATE, False)
    assert result == ExecutionReadiness.CONDITIONAL_OPPORTUNITY


def test_moderate_confidence_is_conditional():
    result = classify_execution_readiness(Bias.BULLISH, 55.0, RiskLevel.MODERATE, None)
    assert result == ExecutionReadiness.CONDITIONAL_OPPORTUNITY


def test_low_but_not_no_trade_confidence_is_watchlist():
    result = classify_execution_readiness(Bias.BULLISH, 35.0, RiskLevel.MODERATE, None)
    assert result == ExecutionReadiness.WATCHLIST


# --- build_institutional_commentary ---

def test_commentary_uses_alignment_line_when_present():
    evidence = ["Institutional Alignment: commercial and speculative positioning support the same direction, increasing conviction."]
    commentary = build_institutional_commentary(
        "Gold", Bias.BULLISH, 80.0, ExecutionReadiness.HIGH_CONVICTION, evidence, [],
    )
    assert "Institutional Alignment" in commentary
    assert "chart confirms" in commentary


def test_commentary_falls_back_to_generic_framing_without_alignment_data():
    commentary = build_institutional_commentary(
        "AAPL", Bias.BULLISH, 70.0, ExecutionReadiness.CONDITIONAL_OPPORTUNITY, [], [],
    )
    assert "AAPL" in commentary
    assert "technical confirmation is required" in commentary.lower()


def test_commentary_no_trade_mentions_capital_preservation():
    commentary = build_institutional_commentary(
        "BTC", Bias.NEUTRAL, 20.0, ExecutionReadiness.NO_TRADE, [], [],
    )
    assert "capital preservation" in commentary.lower()
