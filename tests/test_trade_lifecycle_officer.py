from datetime import datetime, timezone

from agents.trade_lifecycle_officer import evaluate_lifecycle
from models.open_trade import OpenTrade, TradeDirection
from models.report import AgentReport, Bias, RiskLevel
from models.trade_decision import TradeHealth


def _open_long(**overrides):
    defaults = dict(
        id=1, asset_or_theme="Gold", direction=TradeDirection.LONG,
        entry_technical_bias_score=60.0, entry_fundamental_bias_score=70.0, entry_risk_score=70.0,
        entry_market_structure_note="Broke above 2050", stop_loss_level=2020.0, entry_price=2060.0,
        opened_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return OpenTrade(**defaults)


def _tech_report(bias_score, risk_level=RiskLevel.MODERATE):
    return AgentReport(
        department="Chief Technical Officer", asset_or_theme="Gold", bias=Bias.NEUTRAL,
        bias_score=bias_score, confidence=80, risk_level=risk_level, catalysts=[], risks=[], evidence=[],
    )


def test_healthy_trade_with_no_conditions_fired_is_excellent():
    trade = _open_long()
    health, reasons = evaluate_lifecycle(trade, _tech_report(65.0), current_fundamental_score=70.0, current_risk_score=70.0)
    assert health == TradeHealth.EXCELLENT
    assert reasons == []


def test_does_not_downgrade_on_a_single_noisy_condition():
    # Only the technical trend has moved against the thesis; nothing else has.
    trade = _open_long()
    health, reasons = evaluate_lifecycle(trade, _tech_report(20.0), current_fundamental_score=70.0, current_risk_score=70.0)
    assert health == TradeHealth.HEALTHY  # not WEAKENING/CRITICAL off one signal
    assert len(reasons) == 1


def test_downgrades_to_weakening_when_two_conditions_confirm():
    trade = _open_long()
    # Technical trend reversed AND fundamental thesis reversed
    health, reasons = evaluate_lifecycle(trade, _tech_report(20.0), current_fundamental_score=30.0, current_risk_score=70.0)
    assert health == TradeHealth.WEAKENING
    assert len(reasons) == 2


def test_stop_loss_breach_is_always_critical_regardless_of_other_conditions():
    trade = _open_long()
    health, reasons = evaluate_lifecycle(trade, _tech_report(65.0), current_fundamental_score=70.0, current_risk_score=70.0, current_price=2015.0)
    assert health == TradeHealth.CRITICAL
    assert any("stop-loss" in r.lower() for r in reasons)


def test_short_trade_direction_flips_adverse_delta_logic():
    trade = _open_long(direction=TradeDirection.SHORT, entry_technical_bias_score=-60.0)
    # For a short, technical bias_score RISING is adverse (price strengthening against the short)
    health, reasons = evaluate_lifecycle(trade, _tech_report(20.0), current_fundamental_score=70.0, current_risk_score=70.0)
    assert len(reasons) == 1
    assert "against the short thesis" in reasons[0]
