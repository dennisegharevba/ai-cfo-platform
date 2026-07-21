from models.report import AgentReport, Bias, RiskLevel
from models.trade_decision import ExecutionRating
from agents import trade_scoring


def _report(department, bias_score, confidence=80.0, risk_level=RiskLevel.MODERATE, catalysts=None, risks=None, evidence=None):
    return AgentReport(
        department=department, asset_or_theme="TEST", bias=Bias.NEUTRAL, bias_score=bias_score,
        confidence=confidence, risk_level=risk_level, catalysts=catalysts or [], risks=risks or [],
        evidence=evidence or [],
    )


def test_fundamental_score_averages_only_fundamental_departments():
    reports = [
        _report("Chief Macro Officer", 40),
        _report("Chief Commodity Analyst", 40),
        _report("Chief Technical Officer", 100),  # must be excluded from fundamental
    ]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert score == 70.0  # bias_score 40 -> 70 on the 0-100 scale, both agree
    assert "Chief Technical Officer" not in contributing
    assert set(contributing) == {"Chief Macro Officer", "Chief Commodity Analyst"}


def test_fundamental_score_defaults_neutral_with_no_usable_reports():
    reports = [_report("Chief Macro Officer", 40, confidence=0.0)]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert score == 50.0
    assert contributing == []
    assert excluded == ["Chief Macro Officer"]


def test_technical_score_maps_bias_score():
    tech = _report("Chief Technical Officer", 60)
    score, contributing, excluded = trade_scoring.technical_score(tech)
    assert score == 80.0
    assert contributing == ["Chief Technical Officer"]


def test_technical_score_neutral_when_missing():
    score, contributing, excluded = trade_scoring.technical_score(None)
    assert score == 50.0
    assert excluded == ["Chief Technical Officer"]


def test_risk_score_uses_worst_risk_level_and_penalizes_extra_flags():
    reports = [
        _report("Chief Asset Risk Officer", 0, risk_level=RiskLevel.ELEVATED, risks=["ATR expansion", "Weekend gap risk elevated"]),
    ]
    score, contributing, excluded = trade_scoring.risk_score(reports)
    # base 45 (ELEVATED) - 5 (one extra flag beyond the first) = 40
    assert score == 40.0
    assert contributing == ["Chief Asset Risk Officer"]


def test_risk_score_high_risk_floors_correctly_with_many_flags():
    reports = [
        _report("Chief Asset Risk Officer", 0, risk_level=RiskLevel.HIGH, risks=["a", "b", "c", "d", "e", "f", "g"]),
    ]
    score, _, _ = trade_scoring.risk_score(reports)
    assert score >= 0.0  # never negative
    assert score == max(0.0, 20.0 - 6 * 5.0)


def test_overall_score_is_weighted_blend():
    assert trade_scoring.overall_score(80, 60, 100) == round(80 * 0.4 + 60 * 0.4 + 100 * 0.2, 1)


def test_entry_confirmation_all_fail_without_technical_report():
    ec = trade_scoring.build_entry_confirmation(None, fundamental_score_value=80, risk_score_value=70)
    assert not ec.trend_alignment
    assert not ec.breakout_confirmed
    assert ec.risk_acceptable  # risk was fine even without a technical report


def test_entry_confirmation_passes_when_trend_and_momentum_agree():
    tech = _report(
        "Chief Technical Officer", 40, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        evidence=["MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )
    ec = trade_scoring.build_entry_confirmation(tech, fundamental_score_value=70, risk_score_value=70)
    assert ec.trend_alignment
    assert ec.market_structure_confirmed
    assert ec.all_passed()


def test_execution_rating_never_enters_on_weak_technical_confirmation():
    ec = trade_scoring.build_entry_confirmation(None, fundamental_score_value=90, risk_score_value=90)
    rating = trade_scoring.execution_rating(90, 90, 90, ec)
    assert rating != ExecutionRating.ENTER_NOW


def test_execution_rating_avoids_when_bias_too_weak():
    from models.trade_decision import EntryConfirmation
    ec = EntryConfirmation(
        trend_alignment=True, market_structure_confirmed=True, breakout_confirmed=True,
        volume_confirmed=True, liquidity_confirmed=True, macro_alignment=True,
        risk_acceptable=True, minimum_rr_achieved=True,
    )
    rating = trade_scoring.execution_rating(51, 50, 90, ec)  # both scores near-neutral
    assert rating == ExecutionRating.AVOID


def test_trade_grade_caps_on_weakest_leg_not_average():
    # High overall score, but risk is terrible -> should NOT be top-tier
    grade = trade_scoring.trade_grade(overall_score_value=85, fundamental_score_value=90, technical_score_value=90, risk_score_value=15)
    assert grade.value in ("C", "D")
