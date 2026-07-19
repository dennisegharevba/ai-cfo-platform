"""
Risk Officer page — build a small portfolio interactively and run the
Chief Risk Officer against it using real Yahoo Finance price history.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from dashboard.dashboard_utils import get_manager, risk_badge
from config.settings import MIN_DATA_QUALITY
from connectors.yahoo_history_connector import YahooHistoryConnector
from agents.chief_risk_officer import ChiefRiskOfficer
from models.portfolio import Portfolio, Position

st.set_page_config(page_title="Risk Officer — AI CFO Platform", page_icon="⚖️", layout="wide")
st.title("⚖️ Chief Risk Officer")
st.caption("Portfolio-level concentration, volatility, VaR, drawdown, and correlation. Never gives a directional view — see docs/ARCHITECTURE_PHASE6.md.")

manager = get_manager()

st.subheader("Build a portfolio")
default_df = pd.DataFrame([
    {"Symbol": "SPY", "Quantity": 50},
    {"Symbol": "AAPL", "Quantity": 20},
    {"Symbol": "GLD", "Quantity": 30},
    {"Symbol": "TLT", "Quantity": 25},
])
edited_df = st.data_editor(default_df, num_rows="dynamic", width="stretch")

if st.button("Run Chief Risk Officer", type="primary"):
    positions = []
    for _, row in edited_df.iterrows():
        symbol = str(row["Symbol"]).strip().upper()
        if not symbol:
            continue
        try:
            quantity = float(row["Quantity"])
        except (TypeError, ValueError):
            continue
        positions.append(Position(symbol=symbol, quantity=quantity))
        key = f"PRICE_HISTORY_{symbol}"
        if not manager.is_registered(key):
            manager.register(key, primary=YahooHistoryConnector(symbol, period="6mo", interval="1d"))

    if not positions:
        st.warning("Add at least one position with a symbol and quantity.")
    else:
        portfolio = Portfolio(name="Dashboard Portfolio", positions=positions)
        with st.spinner("Fetching price history and computing risk metrics..."):
            report = ChiefRiskOfficer(manager, min_quality=MIN_DATA_QUALITY).analyze_portfolio(portfolio)
        st.session_state["last_risk_report"] = report

report = st.session_state.get("last_risk_report")
if report is not None:
    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("Confidence", f"{report.confidence:.0f}/100")
    col2.markdown(f"**Risk Level**\n\n{risk_badge(report.risk_level.value)}")

    st.markdown("**Evidence**")
    for e in report.evidence:
        st.markdown(f"- {e}")
    if report.catalysts:
        st.markdown("**Catalysts**")
        for c in report.catalysts:
            st.markdown(f"- {c}")
    if report.risks:
        st.markdown("**Risks**")
        for r in report.risks:
            st.markdown(f"- {r}")
    if report.data_gaps:
        st.warning("Data gaps: " + "; ".join(report.data_gaps))
