"""
Tests for agents/factor_narrative.py — the 2026-09-17 fix for a direct
user complaint that catalysts/risks were score labels ("Core CPI is
supportive (score +12.3)") rather than real fundamental interpretation.
"""

from datetime import datetime, timezone

from models.fundamental_factor import FundamentalFactor, FactorBias
from agents.factor_narrative import describe_factor, format_value


def _factor(**overrides) -> FundamentalFactor:
    defaults = dict(
        name="Core CPI (YoY)",
        category="Macroeconomic",
        current_value=3.2,
        previous_value=3.0,
        score=-14.2,
        bias=FactorBias.BEARISH,
        importance_weight=8.0,
        confidence=75.0,
        source="FRED",
        last_updated=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return FundamentalFactor(**defaults)


def test_format_value_uses_the_factors_real_unit():
    assert format_value(3.2, "%") == "3.2%"
    assert format_value(28500.0, "$B") == "$28,500B"
    assert format_value(159432.0, "K") == "159,432K"


def test_format_value_never_fabricates_a_missing_value():
    assert format_value(None, "%") == "n/a"


def test_describe_factor_includes_the_real_current_value_and_change():
    line = describe_factor(_factor(), unit="%", bullish_meaning="cooling", bearish_meaning="hot")
    assert "3.2%" in line
    assert "+0.2" in line  # real change vs. the old template, which never showed this at all


def test_describe_factor_never_uses_the_old_score_label_template():
    line = describe_factor(_factor(), unit="%", bullish_meaning="cooling", bearish_meaning="hot")
    assert "is a headwind (score" not in line
    assert "is supportive (score" not in line


def test_describe_factor_only_shows_the_meaning_matching_the_actual_bias():
    bearish_line = describe_factor(
        _factor(bias=FactorBias.BEARISH), unit="%", bullish_meaning="cooling text", bearish_meaning="hot text",
    )
    assert "hot text" in bearish_line
    assert "cooling text" not in bearish_line

    bullish_line = describe_factor(
        _factor(bias=FactorBias.BULLISH), unit="%", bullish_meaning="cooling text", bearish_meaning="hot text",
    )
    assert "cooling text" in bullish_line
    assert "hot text" not in bullish_line


def test_describe_factor_neutral_factor_gets_no_meaning_clause():
    line = describe_factor(
        _factor(bias=FactorBias.NEUTRAL), unit="%", bullish_meaning="cooling text", bearish_meaning="hot text",
    )
    assert "cooling text" not in line
    assert "hot text" not in line
    assert "3.2%" in line  # still shows the real number


def test_describe_factor_handles_missing_previous_value_without_crashing():
    line = describe_factor(_factor(previous_value=None), unit="%", bullish_meaning="a", bearish_meaning="b")
    assert "vs. prior reading" not in line
    assert "3.2%" in line
