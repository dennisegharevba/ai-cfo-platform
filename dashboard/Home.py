"""
AI CFO Platform — Dashboard home page.

Run with:
    streamlit run dashboard/Home.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from config.settings import FRED_API_KEY, SEC_USER_AGENT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

st.set_page_config(page_title="AI CFO Platform", page_icon="📊", layout="wide")

st.title("📊 AI Chief Fundamental Officer Platform")
st.caption("Institutional-grade multi-agent research — never places trades, only produces research and alerts.")

st.markdown(
    """
This dashboard surfaces the full pipeline built across Phases 1-9:

1. **Data Health** — live status of every registered data source (freshness, quality score, validation)
2. **Department Reports** — run any single-asset Chief Officer live against real data
3. **Strategy Synthesis** — the Chief Strategy Officer's cross-department resolution
4. **Risk Officer** — build a small portfolio and see concentration/volatility/VaR/drawdown/correlation
5. **Performance & Learning** — historical department/strategy performance from recorded outcomes
6. **Alerts & Execution** — the Chief Execution Officer's gating logic, and (optionally) real Telegram sends

Use the sidebar to navigate between pages.
"""
)

st.divider()
st.subheader("Configuration status")

col1, col2, col3, col4 = st.columns(4)
col1.metric("FRED API Key", "✅ Set" if FRED_API_KEY else "⚠️ Not set")
col2.metric("SEC User-Agent", "✅ Set" if SEC_USER_AGENT else "⚠️ Not set")
col3.metric("Telegram Bot Token", "✅ Set" if TELEGRAM_BOT_TOKEN else "⚠️ Not set")
col4.metric("Telegram Chat ID", "✅ Set" if TELEGRAM_CHAT_ID else "⚠️ Not set")

if not FRED_API_KEY or not SEC_USER_AGENT:
    st.info(
        "Some pages need a free FRED API key and/or a descriptive SEC User-Agent to fetch live data. "
        "Copy `.env.example` to `.env` and fill these in — see docs/CONFIGURATION.md."
    )

st.divider()
st.caption(
    "This platform never places trades automatically. Every page here reads real data through the "
    "Data Integrity & Refresh Manager (Phase 1), which blocks any analysis on stale, unvalidated, or "
    "missing data rather than fabricating a result."
)
