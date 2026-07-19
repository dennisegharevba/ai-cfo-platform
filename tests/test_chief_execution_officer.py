from unittest.mock import patch, MagicMock

from agents.chief_execution_officer import ChiefExecutionOfficer
from models.report import Bias, RiskLevel
from models.strategy_report import StrategyReport
from telegram.telegram_alerter import TelegramAlerter, TelegramError


def _strategy_report(
    bias=Bias.BULLISH, bias_score=50.0, confidence_score=80.0, risk_level=RiskLevel.MODERATE,
    contributing=None, excluded=None, catalysts=None, risks=None,
):
    return StrategyReport(
        asset_or_theme="Gold",
        overall_market_score=75.0,
        confidence_score=confidence_score,
        risk_level=risk_level,
        bias=bias,
        bias_score=bias_score,
        trade_thesis="Test thesis",
        investment_committee_summary="Test summary",
        catalysts=catalysts or ["Some catalyst"],
        risks=risks or ["Some risk"],
        contributing_departments=contributing if contributing is not None else ["Chief Macro Officer", "Chief Technical Officer"],
        excluded_departments=excluded or [],
    )


def test_high_confidence_strong_bias_low_risk_passes():
    officer = ChiefExecutionOfficer()
    decision = officer.evaluate(_strategy_report())
    assert decision.should_alert is True
    assert decision.blocking_reasons == []


def test_low_confidence_blocks():
    officer = ChiefExecutionOfficer(min_confidence=65.0)
    decision = officer.evaluate(_strategy_report(confidence_score=50.0))
    assert decision.should_alert is False
    assert any("confidence" in r for r in decision.blocking_reasons)


def test_neutral_bias_blocks():
    officer = ChiefExecutionOfficer()
    decision = officer.evaluate(_strategy_report(bias=Bias.NEUTRAL, bias_score=5.0))
    assert decision.should_alert is False
    assert any("neutral" in r.lower() or "weak" in r.lower() for r in decision.blocking_reasons)


def test_high_risk_blocks_by_default():
    officer = ChiefExecutionOfficer()
    decision = officer.evaluate(_strategy_report(risk_level=RiskLevel.HIGH))
    assert decision.should_alert is False
    assert any("risk" in r.lower() for r in decision.blocking_reasons)


def test_elevated_risk_passes_by_default():
    officer = ChiefExecutionOfficer()
    decision = officer.evaluate(_strategy_report(risk_level=RiskLevel.ELEVATED))
    assert decision.should_alert is True


def test_custom_risk_ceiling_blocks_elevated():
    officer = ChiefExecutionOfficer(max_acceptable_risk=RiskLevel.MODERATE)
    decision = officer.evaluate(_strategy_report(risk_level=RiskLevel.ELEVATED))
    assert decision.should_alert is False


def test_too_many_excluded_departments_blocks():
    officer = ChiefExecutionOfficer()
    decision = officer.evaluate(_strategy_report(
        contributing=["Chief Macro Officer"],
        excluded=["Chief Bond Strategist", "Chief Technical Officer"],
    ))
    assert decision.should_alert is False
    assert any("lacked usable data" in r for r in decision.blocking_reasons)


def test_multiple_blocking_reasons_all_recorded():
    officer = ChiefExecutionOfficer()
    decision = officer.evaluate(_strategy_report(confidence_score=30.0, risk_level=RiskLevel.HIGH))
    assert decision.should_alert is False
    assert len(decision.blocking_reasons) == 2


def test_format_alert_message_includes_required_fields():
    officer = ChiefExecutionOfficer()
    message = officer.format_alert_message(_strategy_report())
    assert "Gold" in message
    assert "BULLISH" in message
    assert "Confidence" in message
    assert "Risk Level" in message
    assert "Some catalyst" in message
    assert "Some risk" in message


def test_process_sends_when_gate_passes_and_alerter_configured():
    with patch("telegram.telegram_alerter.requests.post",
               return_value=MagicMock(json=lambda: {"ok": True}, raise_for_status=lambda: None)):
        alerter = TelegramAlerter(bot_token="FAKE", chat_id="123")
        officer = ChiefExecutionOfficer(alerter=alerter)
        decision = officer.process(_strategy_report())
    assert decision.should_alert is True
    assert decision.alert_sent is True
    assert decision.send_error == ""


def test_process_does_not_send_when_gate_fails():
    alerter = TelegramAlerter(bot_token="FAKE", chat_id="123")
    officer = ChiefExecutionOfficer(alerter=alerter, min_confidence=99.0)
    with patch.object(alerter, "send_message") as mock_send:
        decision = officer.process(_strategy_report(confidence_score=50.0))
    mock_send.assert_not_called()
    assert decision.should_alert is False
    assert decision.alert_sent is False


def test_process_records_send_failure_without_crashing():
    alerter = TelegramAlerter(bot_token="FAKE", chat_id="123")
    officer = ChiefExecutionOfficer(alerter=alerter)
    with patch.object(alerter, "send_message", side_effect=TelegramError("boom")):
        decision = officer.process(_strategy_report())
    assert decision.should_alert is True   # gate passed
    assert decision.alert_sent is False    # but the send itself failed
    assert "boom" in decision.send_error


def test_process_without_alerter_still_evaluates_but_does_not_send():
    officer = ChiefExecutionOfficer(alerter=None)
    decision = officer.process(_strategy_report())
    assert decision.should_alert is True
    assert decision.alert_sent is False
