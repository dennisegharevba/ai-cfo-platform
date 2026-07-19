"""
Performance & Learning page — records this session's department/strategy
reports into a real on-disk SQLite database via the Chief Learning Officer,
then surfaces performance analytics and lets the user log outcomes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import get_learning_officer

st.set_page_config(page_title="Performance & Learning — AI CFO Platform", page_icon="📚", layout="wide")
st.title("📚 Performance & Learning")
st.caption("The Chief Learning Officer: persists every report and lets you record realized outcomes.")

officer = get_learning_officer()

st.subheader("Record this session's reports")
col1, col2 = st.columns(2)

with col1:
    agent_reports = st.session_state.get("last_agent_reports", [])
    st.caption(f"{len(agent_reports)} department report(s) in this session's pool.")
    if st.button("Record all department reports"):
        for r in agent_reports:
            officer.record_agent_report(r)
        st.success(f"Recorded {len(agent_reports)} department report(s).")

with col2:
    strategy_report = st.session_state.get("last_strategy_report")
    st.caption("Strategy report: " + (strategy_report.asset_or_theme if strategy_report else "none yet"))
    if strategy_report and st.button("Record strategy report"):
        sr_id = officer.record_strategy_report(strategy_report)
        st.session_state["last_strategy_report_id"] = sr_id
        st.success(f"Recorded as strategy_report_id={sr_id}.")

st.divider()
st.subheader("Log an outcome")
st.caption(
    "This platform never places trades, so outcomes are judged manually against what actually "
    "happened in the market — not computed automatically."
)
with st.form("record_outcome_form"):
    sr_id_input = st.number_input("Strategy report ID", min_value=1, step=1,
                                    value=st.session_state.get("last_strategy_report_id", 1))
    realized_return = st.number_input("Realized return (%)", value=0.0, step=0.1, format="%.2f")
    was_correct = st.selectbox("Was the thesis correct?", ["Not yet judged", "Correct", "Incorrect"])
    notes = st.text_input("Notes", value="")
    submitted = st.form_submit_button("Record outcome")
    if submitted:
        judged = None if was_correct == "Not yet judged" else (was_correct == "Correct")
        officer.record_outcome(int(sr_id_input), realized_return_pct=realized_return, was_correct=judged, notes=notes)
        st.success(f"Outcome recorded for strategy_report_id={int(sr_id_input)}.")

st.divider()
st.subheader("Department performance")
dept = st.text_input("Department name (blank = all)", value="")
summary = officer.department_performance_summary(department=dept or None)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Reports", summary["report_count"])
c2.metric("Avg confidence", summary["average_confidence"])
c3.metric("Degraded %", f"{summary['degraded_report_pct']}%")
c4.write("**Bias distribution**")
c4.json(summary["bias_distribution"])

st.divider()
st.subheader("Strategy accuracy")
asset_filter = st.text_input("Asset/theme (blank = all)", value="")
accuracy = officer.strategy_accuracy_summary(asset_or_theme=asset_filter or None)
c1, c2 = st.columns(2)
c1.metric("Judged outcomes", accuracy["judged_outcome_count"])
c2.metric("Win rate", f"{accuracy['win_rate_pct']}%" if accuracy["win_rate_pct"] is not None else "—")
if accuracy["average_realized_return_pct"] is not None:
    st.metric("Average realized return", f"{accuracy['average_realized_return_pct']:+.2f}%")
