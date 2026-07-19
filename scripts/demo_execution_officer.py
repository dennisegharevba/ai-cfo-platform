"""
Phase 9 demo: shows the Chief Execution Officer's gating logic against two
scenarios — one that clears every threshold and one that gets blocked —
using illustrative StrategyReports (same style as demo_strategy_officer.py
and demo_learning_officer.py).

This demo does NOT actually send a Telegram message unless you provide real
credentials, since accidentally spamming a real chat while testing would be
worse than the demo just printing what WOULD have been sent. Pass
--send-real to actually send (requires TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID
in .env).

Run:
    python scripts/demo_execution_officer.py
    python scripts/demo_execution_officer.py --send-real
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from agents.chief_execution_officer import ChiefExecutionOfficer
from models.report import Bias, RiskLevel
from models.strategy_report import StrategyReport
from telegram.telegram_alerter import TelegramAlerter


def _strategy_report(bias, bias_score, confidence_score, risk_level, contributing, excluded=None):
    return StrategyReport(
        asset_or_theme="Gold",
        overall_market_score=(bias_score + 100) / 2,
        confidence_score=confidence_score,
        risk_level=risk_level,
        bias=bias,
        bias_score=bias_score,
        trade_thesis=f"Gold: {bias.value} bias (score {bias_score:+.1f}) with {confidence_score:.0f} confidence.",
        investment_committee_summary="Illustrative example for the Phase 9 demo.",
        catalysts=["Building speculative length reflects growing bullish conviction"],
        risks=["Portfolio volatility is elevated"],
        contributing_departments=contributing,
        excluded_departments=excluded or [],
    )


def print_decision(label, decision):
    print(f"\n--- {label} ---")
    print(f"  should_alert: {decision.should_alert}")
    if decision.blocking_reasons:
        print("  Blocked because:")
        for r in decision.blocking_reasons:
            print(f"    - {r}")
    print(f"  alert_sent: {decision.alert_sent}")
    if decision.send_error:
        print(f"  send_error: {decision.send_error}")


def main():
    send_real = "--send-real" in sys.argv

    alerter = None
    if send_real:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("--send-real was passed but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are not set in .env. Exiting.")
            return
        alerter = TelegramAlerter(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)

    officer = ChiefExecutionOfficer(alerter=alerter)

    print("\n=== AI CFO Platform — Phase 9: Chief Execution Officer demo ===")
    if not send_real:
        print("(No Telegram credentials in use — pass --send-real with a configured .env to actually send)")

    passing_report = _strategy_report(
        bias=Bias.BULLISH, bias_score=60.0, confidence_score=78.0, risk_level=RiskLevel.MODERATE,
        contributing=["Chief Macro Officer", "Chief Commodity Analyst", "Chief Technical Officer"],
    )
    decision = officer.process(passing_report)
    print_decision("Scenario 1: clears every threshold", decision)
    if decision.should_alert:
        print("\n  Message that would be sent:\n")
        for line in officer.format_alert_message(passing_report).split("\n"):
            print(f"    {line}")

    blocked_report = _strategy_report(
        bias=Bias.BULLISH, bias_score=25.0, confidence_score=45.0, risk_level=RiskLevel.HIGH,
        contributing=["Chief Macro Officer"],
        excluded=["Chief Commodity Analyst", "Chief Technical Officer"],
    )
    decision2 = officer.process(blocked_report)
    print_decision("Scenario 2: low confidence + high risk + missing data", decision2)


if __name__ == "__main__":
    main()
