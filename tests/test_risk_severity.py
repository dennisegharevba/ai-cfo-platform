from agents.risk_severity import worse_risk_level, worst_of
from models.report import RiskLevel


def test_worse_risk_level_picks_more_severe():
    assert worse_risk_level(RiskLevel.LOW, RiskLevel.HIGH) == RiskLevel.HIGH
    assert worse_risk_level(RiskLevel.HIGH, RiskLevel.LOW) == RiskLevel.HIGH
    assert worse_risk_level(RiskLevel.MODERATE, RiskLevel.ELEVATED) == RiskLevel.ELEVATED


def test_worse_risk_level_equal_returns_same():
    assert worse_risk_level(RiskLevel.MODERATE, RiskLevel.MODERATE) == RiskLevel.MODERATE


def test_worst_of_empty_defaults_to_low():
    assert worst_of([]) == RiskLevel.LOW


def test_worst_of_picks_max_severity_across_many():
    levels = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.ELEVATED]
    assert worst_of(levels) == RiskLevel.HIGH


def test_worst_of_all_low_stays_low():
    assert worst_of([RiskLevel.LOW, RiskLevel.LOW]) == RiskLevel.LOW
