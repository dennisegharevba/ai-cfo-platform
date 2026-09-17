from datetime import date

from agents.chief_seasonality_officer import ChiefSeasonalityOfficer
from models.report import Bias, RiskLevel


def test_configured_asset_produces_a_scored_report():
    officer = ChiefSeasonalityOfficer(reference_date=date(2026, 9, 15))
    report = officer.analyze("Gold")
    assert report.department == "Chief Seasonality Officer"
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence > 0
    assert len(report.factor_breakdown) == 1
    assert report.data_gaps == []


def test_factor_metadata_reflects_documented_pattern_not_live_data():
    officer = ChiefSeasonalityOfficer(reference_date=date(2026, 9, 15))
    report = officer.analyze("Gold")
    factor = report.factor_breakdown[0]
    assert "September" in factor.name
    assert factor.category == "Seasonality"
    assert factor.forecast_value is None
    assert "documented" in factor.source.lower() or "not live-measured" in factor.source.lower()
    assert factor.importance_weight <= 5.0  # low weight — supporting signal only
    assert len(factor.notes) == 1


def test_unconfigured_asset_yields_honest_neutral_result():
    officer = ChiefSeasonalityOfficer(reference_date=date(2026, 9, 15))
    report = officer.analyze("Some Unlisted Asset")
    assert report.bias == Bias.NEUTRAL
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.factor_breakdown == []
    assert any("no seasonality pattern" in g.lower() for g in report.data_gaps)


def test_different_months_for_same_asset_produce_different_scores():
    bullish_month = ChiefSeasonalityOfficer(reference_date=date(2026, 9, 15)).analyze("Gold")
    bearish_month = ChiefSeasonalityOfficer(reference_date=date(2026, 2, 15)).analyze("Gold")
    assert bullish_month.bias_score != bearish_month.bias_score
    assert bullish_month.bias_score > bearish_month.bias_score


def test_defaults_to_todays_date_when_not_specified():
    officer = ChiefSeasonalityOfficer()
    assert officer.reference_date == date.today()


def test_evidence_includes_reasoning_text():
    officer = ChiefSeasonalityOfficer(reference_date=date(2026, 1, 15))
    report = officer.analyze("Natural Gas")
    assert any("heating" in e.lower() for e in report.evidence)


def test_bearish_month_populates_risks_not_catalysts():
    officer = ChiefSeasonalityOfficer(reference_date=date(2026, 10, 15))
    report = officer.analyze("Corn")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert len(report.risks) == 1
    assert report.catalysts == []
