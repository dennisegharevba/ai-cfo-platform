from agents.fundamental_scoring_engine import score_category
from models.fundamental_factor import FundamentalFactor
from models.report import Bias, RiskLevel


def _factor(name, score, confidence, weight=5.0, category="Macroeconomic"):
    return FundamentalFactor(
        name=name, category=category, score=score, confidence=confidence,
        importance_weight=weight, source="TEST",
    )


def test_empty_factor_list_returns_neutral_high_risk():
    result = score_category("Macroeconomic", [])
    assert result.category_score == 0.0
    assert result.category_confidence == 0.0
    assert result.bias == Bias.NEUTRAL
    assert result.risk_level == RiskLevel.HIGH


def test_all_zero_confidence_factors_returns_neutral_high_risk():
    factors = [_factor("A", 80.0, 0.0), _factor("B", -80.0, 0.0)]
    result = score_category("Macroeconomic", factors)
    assert result.category_score == 0.0
    assert result.risk_level == RiskLevel.HIGH


def test_single_strong_bullish_factor_dominates():
    factors = [_factor("Core CPI", 70.0, 90.0, weight=8.0)]
    result = score_category("Macroeconomic", factors)
    assert result.category_score == 70.0
    assert result.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert result.category_confidence > 0


def test_higher_importance_weight_dominates_the_average():
    # One factor bullish with high importance, one bearish with low importance
    factors = [
        _factor("High Importance Bullish", 80.0, 90.0, weight=9.0),
        _factor("Low Importance Bearish", -80.0, 90.0, weight=1.0),
    ]
    result = score_category("Macroeconomic", factors)
    assert result.category_score > 0  # dominated by the high-importance factor


def test_agreeing_factors_produce_low_disagreement():
    factors = [
        _factor("A", 60.0, 85.0),
        _factor("B", 65.0, 85.0),
        _factor("C", 55.0, 85.0),
    ]
    result = score_category("Macroeconomic", factors)
    assert result.disagreement < 20.0
    assert result.risk_level == RiskLevel.MODERATE


def test_sharply_disagreeing_factors_elevate_risk_and_reduce_confidence():
    factors = [
        _factor("Strongly Bullish", 100.0, 95.0, weight=9.0),
        _factor("Strongly Bearish", -100.0, 95.0, weight=9.0),
    ]
    result = score_category("Macroeconomic", factors)
    assert result.risk_level == RiskLevel.ELEVATED
    assert result.disagreement >= 45.0


def test_zero_confidence_factor_excluded_from_aggregation_entirely():
    # A zero-confidence factor should not drag the score toward it at all
    factors = [
        _factor("Usable Bullish", 80.0, 90.0),
        _factor("Missing Data", -100.0, 0.0),  # should be fully excluded
    ]
    result = score_category("Macroeconomic", factors)
    assert result.category_score == 80.0  # entirely from the usable factor


def test_returned_category_score_retains_original_factor_list():
    factors = [_factor("A", 50.0, 80.0), _factor("B", -50.0, 80.0)]
    result = score_category("Macroeconomic", factors)
    assert result.factors == factors
    assert len(result.factors) == 2


def test_category_name_preserved():
    result = score_category("Commodity Fundamentals", [_factor("A", 10.0, 50.0)])
    assert result.category == "Commodity Fundamentals"
