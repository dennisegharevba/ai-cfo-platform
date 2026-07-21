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
