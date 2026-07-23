from agents.chief_strategy_officer import ChiefStrategyOfficer
from models.report import AgentReport, Bias, RiskLevel, bias_from_score


def _report(department, bias_score, confidence, risk_level=RiskLevel.MODERATE, catalysts=None, risks=None, evidence=None):
    return AgentReport(
        department=department,
        asset_or_theme="TEST",
        bias=bias_from_score(bias_score),
        bias_score=bias_score,
        confidence=confidence,
        risk_level=risk_level,
        catalysts=catalysts or [],
        risks=risks or [],
        evidence=evidence or [],
    )


def test_consensus_bullish_departments_yields_bullish_high_confidence():
    reports = [
        _report("Chief Macro Officer", 70, 80),
        _report("Chief Bond Strategist", 65, 75),
        _report("Chief Equity Analyst", 60, 70),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert result.bias_score > 0
    assert result.overall_market_score > 50
    assert result.confidence_score > 50  # low disagreement -> minimal penalty
    assert set(result.contributing_departments) == {"Chief Macro Officer", "Chief Bond Strategist", "Chief Equity Analyst"}
    assert result.excluded_departments == []


def test_conflicting_departments_reduce_confidence_and_pull_toward_neutral():
    reports = [
        _report("Chief Macro Officer", 90, 90),
        _report("Chief Technical Officer", -90, 90),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    # Technical is weighted 0.7 vs macro's 1.0, so it won't be perfectly neutral,
    # but should be pulled well away from either extreme and confidence should
    # take a real disagreement penalty.
    assert abs(result.bias_score) < 50
    assert result.confidence_score < 90
    assert "divided" in result.trade_thesis.lower() or "disagreement" in result.trade_thesis.lower()


def test_zero_confidence_report_excluded_from_synthesis():
    reports = [
        _report("Chief Macro Officer", 80, 80),
        _report("Chief Equity Analyst", 0, 0),  # no usable data this cycle
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "Chief Equity Analyst" in result.excluded_departments
    assert "Chief Macro Officer" in result.contributing_departments
    assert result.bias_score > 0  # driven entirely by the one usable report


def test_sentiment_and_technical_weighted_lower_by_default():
    officer = ChiefStrategyOfficer()
    assert officer._weight_for("Chief Sentiment Officer") < officer._weight_for("Chief Macro Officer")
    assert officer._weight_for("Chief Technical Officer") < officer._weight_for("Chief Macro Officer")


def test_custom_department_weights_override_defaults():
    officer = ChiefStrategyOfficer(department_weights={"Chief Technical Officer": 1.5})
    assert officer._weight_for("Chief Technical Officer") == 1.5


def test_risk_report_excluded_from_bias_but_escalates_risk_level():
    reports = [_report("Chief Macro Officer", 80, 80, risk_level=RiskLevel.LOW)]
    risk_report = _report("Chief Risk Officer", 0, 70, risk_level=RiskLevel.HIGH, risks=["Severe drawdown"])
    result = ChiefStrategyOfficer().synthesize("TEST", reports, risk_report=risk_report)
    assert result.bias_score > 0  # unaffected by the (always-neutral) risk report's bias
    assert result.risk_level == RiskLevel.HIGH  # escalated by the risk report
    assert "Severe drawdown" in result.risks
    assert "Chief Risk Officer" not in result.contributing_departments  # never counted as a directional voter


def test_empty_reports_yields_neutral_zero_confidence():
    result = ChiefStrategyOfficer().synthesize("TEST", [])
    assert result.bias == Bias.NEUTRAL
    assert result.bias_score == 0.0
    assert result.confidence_score == 0.0
    assert "no thesis" in result.trade_thesis.lower()


def test_catalysts_and_risks_deduped_and_capped():
    reports = [
        _report("Chief Macro Officer", 50, 80, catalysts=["Same catalyst", "Unique A"]),
        _report("Chief Bond Strategist", 50, 80, catalysts=["Same catalyst", "Unique B"]),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.catalysts.count("Same catalyst") == 1
    assert "Unique A" in result.catalysts
    assert "Unique B" in result.catalysts


def test_investment_committee_summary_mentions_key_fields():
    reports = [_report("Chief Macro Officer", 60, 80, risks=["Some risk"])]
    result = ChiefStrategyOfficer().synthesize("Gold", reports)
    assert "Gold" in result.investment_committee_summary
    assert "Overall Market Score" in result.investment_committee_summary
    assert "Some risk" in result.investment_committee_summary


def test_execution_readiness_high_conviction_when_technical_confirms():
    reports = [
        _report("Chief Macro Officer", 80, 85, risk_level=RiskLevel.LOW),
        _report("Chief Technical Officer", 60, 80, risk_level=RiskLevel.LOW),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.execution_readiness == "high_conviction"


def test_execution_readiness_conditional_when_technical_disagrees():
    reports = [
        _report("Chief Macro Officer", 85, 90, risk_level=RiskLevel.LOW),
        _report("Chief Technical Officer", -85, 90, risk_level=RiskLevel.LOW),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    # Macro (weight 1.0) dominates Technical (weight 0.7), so bias stays
    # bullish overall — but the disagreeing technical read should still
    # block a "high_conviction" call.
    assert result.execution_readiness != "high_conviction"


def test_execution_readiness_no_trade_when_neutral():
    reports = [_report("Chief Macro Officer", 5, 80)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.execution_readiness == "no_trade"


def test_execution_readiness_no_trade_on_empty_reports():
    result = ChiefStrategyOfficer().synthesize("TEST", [])
    assert result.execution_readiness == "no_trade"


def test_institutional_commentary_surfaces_alignment_evidence():
    reports = [
        _report(
            "Chief Commodity Analyst", 70, 85, risk_level=RiskLevel.MODERATE,
            evidence=["Institutional Alignment: commercial and speculative positioning support the same direction, increasing conviction."],
        ),
    ]
    result = ChiefStrategyOfficer().synthesize("Gold", reports)
    assert "Institutional Alignment" in result.institutional_commentary


def test_institutional_commentary_falls_back_when_no_positioning_department():
    reports = [_report("Chief Macro Officer", 60, 80)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "TEST" in result.institutional_commentary
    assert result.institutional_commentary != ""
