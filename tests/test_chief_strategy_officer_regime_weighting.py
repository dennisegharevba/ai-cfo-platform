from datetime import date

from agents.chief_strategy_officer import ChiefStrategyOfficer
from models.report import AgentReport, Bias, RiskLevel, bias_from_score


def _report(department, bias_score, confidence, risk_level=RiskLevel.MODERATE):
    return AgentReport(
        department=department, asset_or_theme="TEST", bias=bias_from_score(bias_score),
        bias_score=bias_score, confidence=confidence, risk_level=risk_level,
    )


# A guaranteed-normal date: not an earnings-season month (only Jan/Apr/Jul/Oct
# count), and FOMC_MEETING_DATES ships empty so FOMC_WEEK never triggers
# regardless of date.
NORMAL_DATE = date(2026, 2, 15)
# A guaranteed earnings-season date.
EARNINGS_SEASON_DATE = date(2026, 4, 15)


def test_normal_month_leaves_equity_analyst_weight_unchanged():
    reports = [
        _report("Chief Macro Officer", 50, 90),
        _report("Chief Equity Analyst", -50, 90),
    ]
    officer = ChiefStrategyOfficer()
    result_normal = officer.synthesize("TEST", reports, reference_date=NORMAL_DATE)
    # Both departments have equal confidence and default weight (1.0) in a
    # normal month, so a perfectly opposed 50/-50 should land near-neutral.
    assert abs(result_normal.bias_score) < 5.0


def test_earnings_season_boosts_equity_analyst_weight_and_shifts_the_outcome():
    """
    Direct proof the dynamic regime weighting genuinely changes the
    outcome, not just a cosmetic multiplier: the exact same two opposing
    reports produce a DIFFERENT bias_score in an earnings-season month
    than in a normal month, because Chief Equity Analyst's weight is
    boosted 1.3x during earnings season (agents/market_regime.py).
    """
    reports = [
        _report("Chief Macro Officer", 50, 90),
        _report("Chief Equity Analyst", -50, 90),
    ]
    officer = ChiefStrategyOfficer()
    result_normal = officer.synthesize("TEST", reports, reference_date=NORMAL_DATE)
    result_earnings = officer.synthesize("TEST", reports, reference_date=EARNINGS_SEASON_DATE)

    assert result_normal.bias_score != result_earnings.bias_score
    # Equity Analyst is bearish and gets MORE weight during earnings
    # season, so the outcome should shift bearish relative to the normal-month case.
    assert result_earnings.bias_score < result_normal.bias_score


def test_departments_outside_the_regime_mapping_are_never_affected():
    """Chief Bond Strategist has no entry in DEPARTMENT_TO_REGIME_CATEGORY
    — its effective weight must be identical in every regime."""
    reports = [_report("Chief Bond Strategist", 40, 80)]
    officer = ChiefStrategyOfficer()
    result_normal = officer.synthesize("TEST", reports, reference_date=NORMAL_DATE)
    result_earnings = officer.synthesize("TEST", reports, reference_date=EARNINGS_SEASON_DATE)
    assert result_normal.bias_score == result_earnings.bias_score
    assert result_normal.confidence_score == result_earnings.confidence_score


def test_reference_date_defaults_to_today_without_crashing():
    """Not asserting a specific value (today's regime is whatever it is) —
    just proving the default path (no reference_date passed) works at all."""
    reports = [_report("Chief Macro Officer", 50, 90)]
    officer = ChiefStrategyOfficer()
    result = officer.synthesize("TEST", reports)  # no reference_date
    assert result.bias_score != 0.0 or result.confidence_score >= 0.0  # just doesn't crash


def test_fomc_week_boosts_macro_officer_when_a_meeting_date_is_configured(monkeypatch):
    """
    config/fomc_meeting_dates.py ships empty by default (see that file's
    own honest-scope docstring) — this test proves the mechanism works
    correctly WHEN a real date has been configured, by monkeypatching in
    a fake meeting date rather than depending on the real (empty) list.
    """
    import agents.chief_strategy_officer as cso_module

    fomc_date = date(2026, 3, 18)
    monkeypatch.setattr(cso_module, "FOMC_MEETING_DATES", [fomc_date])

    reports = [
        _report("Chief Macro Officer", 50, 90),
        _report("Chief FX Analyst", -50, 90),  # not in the regime mapping — unaffected
    ]
    officer = ChiefStrategyOfficer()
    # 2 days before the meeting -> within FOMC_WINDOW_DAYS_BEFORE=3
    result_fomc_week = officer.synthesize("TEST", reports, reference_date=date(2026, 3, 16))
    result_normal = officer.synthesize("TEST", reports, reference_date=NORMAL_DATE)

    assert result_fomc_week.bias_score != result_normal.bias_score
    # Macro is bullish and gets MORE weight during the FOMC week, so the
    # outcome should shift bullish relative to the normal-week case.
    assert result_fomc_week.bias_score > result_normal.bias_score
