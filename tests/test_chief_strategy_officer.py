from agents.chief_strategy_officer import ChiefStrategyOfficer
from models.report import AgentReport, Bias, RiskLevel, bias_from_score

# NOTE on test determinism: synthesize() defaults reference_date to
# date.today() and applies a REAL dynamic weight multiplier to
# "Chief Equity Analyst" during earnings-season months (Jan/Apr/Jul/Oct —
# see agents/market_regime.py) and to "Chief Macro Officer" during an
# FOMC week (never triggers by default — config/fomc_meeting_dates.py
# ships empty). None of the tests below assert an exact numeric
# bias_score/weight tied to Chief Equity Analyst, so they're safe
# regardless of which month they run in — but any NEW test asserting an
# exact weight-derived number for that department should pass an explicit
# reference_date (see tests/test_chief_strategy_officer_regime_weighting.py
# for the pattern) rather than relying on "today" happening to be a
# normal month.


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
        _report("Chief Sentiment Officer", -90, 90),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    # Sentiment is weighted 0.7 vs macro's 1.0, so it won't be perfectly neutral,
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


def test_sentiment_weighted_lower_by_default():
    officer = ChiefStrategyOfficer()
    assert officer._weight_for("Chief Sentiment Officer") < officer._weight_for("Chief Macro Officer")


def test_cot_departments_weighted_significantly_below_fundamentals():
    officer = ChiefStrategyOfficer()
    macro_weight = officer._weight_for("Chief Macro Officer")
    assert officer._weight_for("Chief Commodity Analyst") < macro_weight
    assert officer._weight_for("Chief FX Analyst") < macro_weight
    # "Significantly" lower, not just marginally — COT is supporting
    # confirmation only, never the primary reason for a trade.
    assert officer._weight_for("Chief Commodity Analyst") <= macro_weight * 0.5
    assert officer._weight_for("Chief FX Analyst") <= macro_weight * 0.5


def test_strong_cot_signal_alone_cannot_dominate_over_fundamentals():
    # A confident opposing fundamental read against an even more confident
    # COT (Commodity) read of moderate magnitude — with COT weighted at 0.4
    # vs Macro's 1.0, the math works out to:
    #   effective weights: Macro = 1.0*0.65=0.65, Commodity = 0.4*1.0=0.40
    #   weighted mean = (-40*0.65 + 60*0.40) / (0.65+0.40) = -1.9 (bearish)
    # Whereas with EQUAL weighting (both at 1.0) it would instead compute to
    # (-40*0.65 + 60*1.0) / (0.65+1.0) = +20.6 (bullish) — proving the COT
    # de-weighting genuinely changes which side wins, not just softens it.
    reports = [
        _report("Chief Macro Officer", -40, 65),
        _report("Chief Commodity Analyst", 60, 100),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.bias_score < 0


def test_unlisted_department_falls_back_to_weight_one():
    # Chief Technical Officer was removed from the platform's main scoring
    # pipeline (per user request) — it no longer has a default weight
    # entry, so any department not explicitly listed just gets 1.0.
    officer = ChiefStrategyOfficer()
    assert officer._weight_for("Chief Technical Officer") == 1.0
    assert officer._weight_for("Some Made Up Department") == 1.0


def test_custom_department_weights_override_defaults():
    officer = ChiefStrategyOfficer(department_weights={"Chief Sentiment Officer": 1.5})
    assert officer._weight_for("Chief Sentiment Officer") == 1.5


def test_risk_report_excluded_from_bias_but_escalates_risk_level():
    reports = [_report("Chief Macro Officer", 80, 80, risk_level=RiskLevel.LOW)]
    risk_report = _report("Chief Risk Officer", 0, 70, risk_level=RiskLevel.HIGH, risks=["Severe drawdown"])
    result = ChiefStrategyOfficer().synthesize("TEST", reports, risk_report=risk_report)
    assert result.bias_score > 0  # unaffected by the (always-neutral) risk report's bias
    assert result.risk_level == RiskLevel.HIGH  # escalated by the risk report
    assert "Severe drawdown" in result.risks
    assert "Chief Risk Officer" not in result.contributing_departments  # never counted as a directional voter


def test_risk_reports_plural_also_excluded_from_bias_but_escalates_risk_level():
    """
    Chief Risk Fundamentals Officer's per-asset volatility/drawdown report
    makes the same kind of claim as the portfolio Chief Risk Officer
    ("how risky", not "which direction") — it uses the new risk_reports
    (plural) parameter and gets the identical treatment.
    """
    reports = [_report("Chief Macro Officer", 80, 80, risk_level=RiskLevel.LOW)]
    volatility_report = _report(
        "Chief Risk Fundamentals Officer", -60, 70, risk_level=RiskLevel.HIGH,
        risks=["Annualized Volatility is elevated"],
    )
    result = ChiefStrategyOfficer().synthesize("TEST", reports, risk_reports=[volatility_report])
    assert result.bias_score > 0  # unaffected by the risk report's own (unrelated) bias_score
    assert result.risk_level == RiskLevel.HIGH
    assert "Annualized Volatility is elevated" in result.risks
    assert "Chief Risk Fundamentals Officer" not in result.contributing_departments


def test_both_risk_report_and_risk_reports_can_be_combined():
    reports = [_report("Chief Macro Officer", 80, 80, risk_level=RiskLevel.LOW)]
    portfolio_risk = _report("Chief Risk Officer", 0, 70, risk_level=RiskLevel.MODERATE, risks=["Concentration risk"])
    asset_risk = _report("Chief Risk Fundamentals Officer", -60, 70, risk_level=RiskLevel.HIGH, risks=["High volatility"])
    result = ChiefStrategyOfficer().synthesize(
        "TEST", reports, risk_report=portfolio_risk, risk_reports=[asset_risk],
    )
    assert result.risk_level == RiskLevel.HIGH  # worst of LOW/MODERATE/HIGH
    assert "Concentration risk" in result.risks
    assert "High volatility" in result.risks
    assert result.bias_score > 0  # neither risk report affects direction


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


def test_execution_readiness_high_conviction_from_strong_single_department():
    # No technical-confirmation gate anymore — Chief Technical Officer was
    # removed from the platform's main scoring pipeline (per user request).
    # A single strong, confident, low-risk fundamental report is enough.
    reports = [_report("Chief Macro Officer", 80, 85, risk_level=RiskLevel.LOW)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.execution_readiness == "high_conviction"


def test_execution_readiness_degrades_when_departments_disagree():
    reports = [
        _report("Chief Macro Officer", 85, 90, risk_level=RiskLevel.LOW),
        _report("Chief Sentiment Officer", -85, 90, risk_level=RiskLevel.LOW),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    # The disagreement penalty should pull confidence below the High
    # Conviction bar even though both individual reports were confident.
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


# --- decision_explanation ("Explain Every Decision") ---

def test_decision_explanation_lists_every_department_with_its_bias():
    reports = [
        _report("Chief Macro Officer", 60, 85),
        _report("Chief FX Analyst", -40, 70, risks=["USD strength headwind"]),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "Chief Macro Officer is bullish" in result.decision_explanation
    assert "Chief FX Analyst is bearish" in result.decision_explanation


def test_decision_explanation_identifies_greatest_influence_by_effective_weight():
    # Chief Macro Officer: weight 1.0 * confidence 0.9 = 0.9 (highest)
    # Chief Sentiment Officer: weight 0.7 * confidence 0.5 = 0.35 (lowest)
    reports = [
        _report("Chief Macro Officer", 50, 90),
        _report("Chief Sentiment Officer", 50, 50),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "Greatest influence on this synthesis: Chief Macro Officer" in result.decision_explanation


def test_decision_explanation_flags_conflicting_departments():
    reports = [
        _report("Chief Macro Officer", 70, 90),
        _report("Chief FX Analyst", -70, 90),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    # Macro (weight 1.0) dominates FX (weight 0.4), so overall bias stays
    # bullish — FX should be flagged as conflicting with that final bias.
    assert "conflicting with the final" in result.decision_explanation
    assert "Chief FX Analyst" in result.decision_explanation


def test_decision_explanation_reports_no_conflict_when_departments_agree():
    reports = [
        _report("Chief Macro Officer", 60, 85),
        _report("Chief Bond Strategist", 55, 80),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "No department meaningfully conflicts" in result.decision_explanation


def test_decision_explanation_includes_strongest_risks_and_invalidation():
    reports = [_report("Chief Macro Officer", -50, 85, risks=["CPI accelerating unexpectedly"])]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "Strongest risks: CPI accelerating unexpectedly" in result.decision_explanation
    assert "could be invalidated if" in result.decision_explanation
    assert "CPI accelerating unexpectedly" in result.decision_explanation


def test_decision_explanation_handles_empty_reports_gracefully():
    result = ChiefStrategyOfficer().synthesize("TEST", [])
    assert "no department contributed usable data" in result.decision_explanation.lower()


def test_decision_explanation_serializes_via_to_dict():
    reports = [_report("Chief Macro Officer", 50, 80)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    d = result.to_dict()
    assert "decision_explanation" in d
    assert d["decision_explanation"] == result.decision_explanation


# --- committee_table / committee_recommendation ("Final Investment Committee") ---

def test_committee_table_weights_sum_to_approximately_100_percent():
    reports = [
        _report("Chief Macro Officer", 60, 90),
        _report("Chief Sentiment Officer", 40, 60),
        _report("Chief Commodity Analyst", 70, 70),
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    total = sum(row["weight_pct"] for row in result.committee_table)
    assert abs(total - 100.0) < 0.5  # allow for independent per-row rounding


def test_committee_table_sorted_by_weight_descending():
    reports = [
        _report("Chief Sentiment Officer", 40, 60),   # weight 0.7*0.6=0.42
        _report("Chief Macro Officer", 60, 90),         # weight 1.0*0.9=0.9 (highest)
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.committee_table[0]["department"] == "Chief Macro Officer"


def test_committee_table_row_has_correct_fields():
    reports = [_report("Chief Macro Officer", 60, 90)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    row = result.committee_table[0]
    assert row["department"] == "Chief Macro Officer"
    assert row["bias"] in ("bullish", "strongly_bullish")
    assert row["weight_pct"] == 100.0  # only one contributor
    assert row["confidence"] == 90


def test_committee_table_empty_when_no_contributing_departments():
    result = ChiefStrategyOfficer().synthesize("TEST", [])
    assert result.committee_table == []


def test_committee_recommendation_long_for_bullish():
    reports = [_report("Chief Macro Officer", 70, 90, risk_level=RiskLevel.LOW)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.committee_recommendation == "Long (research view)"


def test_committee_recommendation_short_for_bearish():
    reports = [_report("Chief Macro Officer", -70, 90, risk_level=RiskLevel.LOW)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.committee_recommendation == "Short (research view)"


def test_committee_recommendation_hold_for_neutral():
    reports = [_report("Chief Macro Officer", 5, 80)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.committee_recommendation == "Hold / No Trade (research view)"


def test_committee_recommendation_never_a_bare_trade_instruction():
    """The platform never places trades — this must always read as a
    research conclusion, never a bare command like 'Long' or 'Buy'."""
    reports = [_report("Chief Macro Officer", 70, 90, risk_level=RiskLevel.LOW)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert "research view" in result.committee_recommendation.lower()


def test_committee_table_serializes_via_to_dict():
    reports = [_report("Chief Macro Officer", 60, 80)]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    d = result.to_dict()
    assert "committee_table" in d
    assert "committee_recommendation" in d
    assert d["committee_table"] == result.committee_table


# --- duplicate-department defensive deduplication ---

def test_duplicate_department_report_is_not_double_weighted():
    """
    Regression test for a real bug found via live testing: the dashboard
    session pool could contain the same department's report twice (e.g.
    after re-running it), and synthesize() had no defense against this —
    a duplicated department would silently count TWICE in the weighted
    bias average, doubling its real influence on the result. Proven
    directly: a duplicated bullish Macro report alongside one bearish
    Equity report should NOT out-weigh what a single (non-duplicated)
    Macro report of the same strength would produce.
    """
    reports_with_duplicate = [
        _report("Chief Macro Officer", 80, 90),
        _report("Chief Macro Officer", 80, 90),  # exact duplicate
        _report("Chief Equity Analyst", -80, 90),
    ]
    reports_without_duplicate = [
        _report("Chief Macro Officer", 80, 90),
        _report("Chief Equity Analyst", -80, 90),
    ]
    result_with_dup = ChiefStrategyOfficer().synthesize("TEST", reports_with_duplicate)
    result_without_dup = ChiefStrategyOfficer().synthesize("TEST", reports_without_duplicate)

    # Same two distinct departments, same scores — the duplicate should
    # have ZERO effect on the outcome once deduplicated.
    assert result_with_dup.bias_score == result_without_dup.bias_score
    assert len(result_with_dup.contributing_departments) == 2


def test_duplicate_department_keeps_the_last_occurrence():
    """When a department appears twice with DIFFERENT data (the realistic
    case — re-running produces a genuinely new report), the most recent
    (last) occurrence should be the one used, matching "re-running
    replaces the previous result" as the expected behavior."""
    reports = [
        _report("Chief Macro Officer", 80, 90),   # stale, should be replaced
        _report("Chief Macro Officer", -50, 70),  # the newer, real result
    ]
    result = ChiefStrategyOfficer().synthesize("TEST", reports)
    assert result.bias_score == -50.0  # only the second (newer) report contributes
    assert result.contributing_departments == ["Chief Macro Officer"]  # not duplicated in the output either


def test_duplicate_risk_report_does_not_duplicate_risks_and_catalysts_text():
    reports = [_report("Chief Macro Officer", 50, 80)]
    risk_report = AgentReport(
        department="Chief Risk Fundamentals Officer", asset_or_theme="TEST", bias=Bias.NEUTRAL,
        bias_score=0.0, confidence=70.0, risk_level=RiskLevel.ELEVATED,
        catalysts=["Low volatility"], risks=["Elevated drawdown risk"],
    )
    duplicated_risk_reports = [risk_report, risk_report]  # the exact same report object, twice
    result = ChiefStrategyOfficer().synthesize("TEST", reports, risk_reports=duplicated_risk_reports)
    assert result.catalysts.count("Low volatility") == 1
    assert result.risks.count("Elevated drawdown risk") == 1
