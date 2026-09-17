from datetime import datetime, timezone, timedelta

from agents.chief_trade_decision_officer import ChiefTradeDecisionOfficer
from database.report_store import ReportStore
from models.open_trade import OpenTrade, TradeDirection
from models.report import AgentReport, Bias, RiskLevel
from models.trade_decision import ExecutionRating, Momentum, TradeHealth


def _macro(bias_score=40, dept="Chief Macro Officer", catalysts=None, risks=None):
    return AgentReport(
        department=dept, asset_or_theme="Gold", bias=Bias.BULLISH, bias_score=bias_score,
        confidence=80, risk_level=RiskLevel.MODERATE, catalysts=catalysts or [], risks=risks or [], evidence=[],
    )


def _confirmed_technical(bias_score=35):
    return AgentReport(
        department="Chief Technical Officer", asset_or_theme="Gold", bias=Bias.BULLISH, bias_score=bias_score,
        confidence=90, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        risks=[],
        evidence=["RSI(14) is 58.0", "MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )


def test_never_enters_on_overall_score_alone_when_technical_unconfirmed():
    """The core principle from spec section 1, as an executable test."""
    reports = [
        _macro(bias_score=80),
        _macro(dept="Chief Commodity Analyst", bias_score=80),
        AgentReport(
            department="Chief Technical Officer", asset_or_theme="Gold", bias=Bias.NEUTRAL, bias_score=0,
            confidence=90, risk_level=RiskLevel.MODERATE, catalysts=[], risks=[],
            evidence=["RSI(14) is 50.0", "MACD histogram is flat (0.00)", "Price structure shows no clear trend (20 SMA vs 50 SMA)"],
        ),
    ]
    decision = ChiefTradeDecisionOfficer().decide("Gold", reports)
    assert decision.overall_score > 65  # overall score IS strong
    assert decision.execution_rating != ExecutionRating.ENTER_NOW  # but rating must not follow it blindly


def test_three_scores_are_independently_visible_not_collapsed():
    reports = [_macro(bias_score=90), _confirmed_technical(bias_score=-90)]
    decision = ChiefTradeDecisionOfficer().decide("Gold", reports)
    # fundamentals bullish, technicals bearish -- both must remain visible and different
    assert decision.fundamental_score > 70
    assert decision.technical_score < 30
    assert decision.fundamental_score != decision.technical_score


def test_full_pipeline_saves_and_reloads_from_store():
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)
    reports = [_macro(bias_score=40), _confirmed_technical()]
    decision = officer.decide("Gold", reports)

    saved = store.get_trade_decisions(asset_or_theme="Gold")
    assert len(saved) == 1
    assert saved[0]["overall_score"] == decision.overall_score
    assert saved[0]["execution_rating"] == decision.execution_rating.value


def test_momentum_is_insufficient_history_on_first_run_then_populated_on_second():
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)
    reports = [_macro(bias_score=40), _confirmed_technical()]

    first = officer.decide("Gold", reports)
    assert first.overall_momentum.momentum == Momentum.INSUFFICIENT_HISTORY

    second = officer.decide("Gold", reports)  # same inputs -> stable, but now WITH history
    assert second.overall_momentum.momentum != Momentum.INSUFFICIENT_HISTORY
    assert second.overall_momentum.previous_score == first.overall_score


def test_open_trade_health_reflects_lifecycle_not_score_alone():
    store = ReportStore(":memory:")
    store.open_trade(OpenTrade(
        id=None, asset_or_theme="Gold", direction=TradeDirection.LONG,
        entry_technical_bias_score=55.0,  # matches _confirmed_technical(bias_score=55) below -> unchanged
        entry_fundamental_bias_score=80.0,  # will diverge from the -10 bias_score report below
        entry_risk_score=50.0,  # matches the neutral default risk_score when no risk desk report exists -> unchanged
        entry_market_structure_note="Broke above resistance", stop_loss_level=None, entry_price=2000.0,
    ))
    officer = ChiefTradeDecisionOfficer(report_store=store)

    # Only ONE structural condition has weakened (fundamental thesis) -- should stay HEALTHY, not CRITICAL,
    # even though the raw overall score has clearly dropped.
    reports = [_macro(bias_score=-10), _confirmed_technical(bias_score=55)]
    decision = officer.decide("Gold", reports)
    assert decision.trade_health in (TradeHealth.HEALTHY, TradeHealth.EXCELLENT)


def test_no_open_trade_reports_not_open():
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)
    reports = [_macro(), _confirmed_technical()]
    decision = officer.decide("Gold", reports)
    assert decision.trade_health == TradeHealth.NOT_OPEN


# --- price_history: the real technical-scoring path ---

def _realistic_uptrend_history(n=60):
    import math
    return list(reversed([
        {"close": 100 + i * 1.2 + math.sin(i * 0.5) * 2, "date": f"2026-01-{(i % 28) + 1:02d}"}
        for i in range(n)
    ]))


def _realistic_downtrend_history(n=60):
    import math
    return list(reversed([
        {"close": 300 - i * 1.2 + math.sin(i * 0.5) * 2, "date": f"2026-01-{(i % 28) + 1:02d}"}
        for i in range(n)
    ]))


def test_decide_uses_real_technical_score_when_price_history_provided():
    """
    Regression test: decide() previously ALWAYS looked for a report named
    'Chief Technical Officer' — a department that was permanently deleted
    from the platform's main pipeline, meaning Technical Score was
    silently stuck at the neutral 50.0 default forever. Proven directly:
    with real price_history supplied, the technical score should NOT be
    exactly 50.0 (the old, permanently-broken default) for a genuine
    trending price series.
    """
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)
    reports = [_macro(bias_score=60)]
    decision = officer.decide("Gold", reports, price_history=_realistic_uptrend_history())
    assert decision.technical_score != 50.0
    assert decision.technical_score > 50.0  # a real uptrend should score bullish


def test_decide_without_price_history_falls_back_to_legacy_neutral_default():
    """The old behavior (no price_history, no matching department report)
    is preserved exactly, for backward compatibility."""
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)
    reports = [_macro(bias_score=60)]
    decision = officer.decide("Gold", reports)  # no price_history
    assert decision.technical_score == 50.0


def test_decide_with_price_history_populates_real_entry_confirmation():
    """The synthetic technical report built from price_history should
    genuinely drive entry_confirmation, not leave it stuck in the
    'no usable technical report' fallback path."""
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)
    reports = [_macro(bias_score=60)]
    decision = officer.decide("Gold", reports, price_history=_realistic_uptrend_history())
    assert decision.entry_confirmation.trend_alignment is True


def test_momentum_explanations_are_component_specific_not_all_identical():
    """
    Regression test for a real bug found via live testing: Fundamental,
    Technical, Risk, and Overall momentum explanations were all showing
    the EXACT SAME "why" text, because all four were fed the same merged
    overall catalysts/risks list — meaning a genuinely FUNDAMENTAL signal
    (COT positioning) was being shown as the "why" for the TECHNICAL
    score's movement too, which is actively misleading (Technical Score
    is computed purely from RSI/MACD/SMA price data and has nothing to do
    with COT positioning).

    Proven directly: a Fundamental-only risk ("crowded long COT
    positioning") and a Technical-only risk (from the real synthetic
    technical report, built from a genuine downtrend) must NOT bleed into
    each other's momentum explanation once both scores have weakened
    enough to have one.
    """
    store = ReportStore(":memory:")
    officer = ChiefTradeDecisionOfficer(report_store=store)

    fundamental_only_risk = "Non-Commercial positioning shows an extreme bullish reading — crowded long"
    reports = [_macro(bias_score=80, risks=[fundamental_only_risk])]

    # First run: establish a baseline (insufficient history -> no explanation yet).
    officer.decide("Gold", reports, price_history=_realistic_uptrend_history())

    # Second run: fundamental and technical both move enough to weaken.
    weaker_reports = [_macro(bias_score=20, risks=[fundamental_only_risk])]
    decision = officer.decide("Gold", weaker_reports, price_history=_realistic_downtrend_history())

    if decision.fundamental_momentum.explanation:
        assert fundamental_only_risk in decision.fundamental_momentum.explanation
        # The Fundamental-only risk must NOT appear in Technical's explanation.
        assert fundamental_only_risk not in decision.technical_momentum.explanation
    if decision.technical_momentum.explanation:
        # Technical's own explanation should come from the real synthetic
        # technical report (RSI/MACD/SMA-based text), not the COT risk.
        assert all(fundamental_only_risk != item for item in decision.technical_momentum.explanation)
