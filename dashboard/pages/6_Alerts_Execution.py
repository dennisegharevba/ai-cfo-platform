"""
Alerts & Execution page — runs the Chief Execution Officer's gating logic
against the most recent Strategy Synthesis result, with adjustable
thresholds, and can optionally send a REAL Telegram alert (behind an
explicit confirmation checkbox — never sent by accident).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from models.report import RiskLevel
from agents.chief_execution_officer import ChiefExecutionOfficer
from telegram.telegram_alerter import TelegramAlerter, TelegramError

st.set_page_config(page_title="Alerts & Execution — AI CFO Platform", page_icon="🚨", layout="wide")
st.title("🚨 Alerts & Execution")
st.caption("The Chief Execution Officer: gates on confidence, bias strength, risk, and data coverage before ever alerting.")

strategy_report = st.session_state.get("last_strategy_report")

if strategy_report is None:
    st.info("No synthesized strategy report yet — go to **Strategy Synthesis** and run it first.")
else:
    st.subheader("Gating thresholds")
    col1, col2, col3, col4 = st.columns(4)
    min_confidence = col1.slider("Min confidence", 0, 100, 65)
    risk_options = [r.value for r in RiskLevel]
    max_risk = col2.selectbox("Max acceptable risk", risk_options, index=risk_options.index("elevated"))
    min_bias_magnitude = col3.slider("Min |bias score|", 0, 100, 15)
    max_excluded_fraction = col4.slider("Max excluded department fraction", 0.0, 1.0, 0.5, step=0.05)

    officer = ChiefExecutionOfficer(
        min_confidence=float(min_confidence),
        max_acceptable_risk=RiskLevel(max_risk),
        min_bias_magnitude=float(min_bias_magnitude),
        max_excluded_fraction=max_excluded_fraction,
    )
    decision = officer.evaluate(strategy_report)

    st.divider()
    if decision.should_alert:
        st.success(f"✅ Would alert on **{strategy_report.asset_or_theme}**")
    else:
        st.error(f"❌ Blocked for **{strategy_report.asset_or_theme}**")
        for reason in decision.blocking_reasons:
            st.markdown(f"- {reason}")

    st.subheader("Alert message preview")
    st.code(officer.format_alert_message(strategy_report), language="markdown")

    if decision.should_alert:
        st.divider()
        st.subheader("Send for real")
        has_creds = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        if not has_creds:
            st.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set in .env — sending is disabled.")
        else:
            confirm = st.checkbox("I understand this will send a real Telegram message right now.")
            if st.button("Send real alert", disabled=not confirm, type="primary"):
                alerter = TelegramAlerter(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
                try:
                    alerter.send_message(officer.format_alert_message(strategy_report))
                    st.success("Alert sent.")
                except TelegramError as exc:
                    st.error(f"Send failed: {exc}")
