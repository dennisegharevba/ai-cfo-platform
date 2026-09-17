"""
AI CFO Platform — Dashboard home page.

Redesigned as a "Market Overview" command-center view: a live summary of
whatever's actually been analyzed this session (grouped by asset, each
with the platform's signature bias gauge), rather than a static
description of what the pages below do. See dashboard/dashboard_utils.py's
render_bias_gauge() docstring and .streamlit/config.toml for the full
design rationale (dark terminal aesthetic + gold accent, chosen because
this platform's own defining feature is precious-metals fundamentals).

Run with:
    streamlit run dashboard/Home.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from config.settings import FRED_API_KEY, SEC_USER_AGENT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from dashboard.dashboard_utils import (
    inject_terminal_css, render_bias_gauge, bias_badge, risk_badge, PLATFORM_COLORS, get_manager,
)
from agents.market_breadth import compute_breadth

st.set_page_config(page_title="AI CFO Platform", page_icon="📊", layout="wide")
inject_terminal_css()

st.markdown(
    f"""
    <div style="border-bottom: 1px solid {PLATFORM_COLORS['accent_gold']}33; padding-bottom: 0.75rem; margin-bottom: 1rem;">
        <span style="color: {PLATFORM_COLORS['accent_gold']}; font-size: 0.78rem; letter-spacing: 0.12em; text-transform: uppercase;">
            Institutional Research Terminal
        </span>
        <h1 style="margin: 0.2rem 0 0 0; font-weight: 700;">AI Chief Fundamental Officer Platform</h1>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Multi-agent macro, commodity, equity, crypto, sentiment, seasonality, and risk research — "
    "never places trades, only produces research and gated alerts."
)

# --- Market Overview: whatever's actually been analyzed this session ---
last_reports = st.session_state.get("last_agent_reports", [])
last_strategy = st.session_state.get("last_strategy_report")

if not last_reports and not last_strategy:
    st.info(
        "No research run yet this session. Head to **Department Reports** to run an individual "
        "Chief Officer, or **Strategy Synthesis** for a cross-department view — both feed this "
        "overview once you've run them."
    )
else:
    if last_strategy is not None:
        st.subheader(f"Latest Synthesis — {last_strategy.asset_or_theme}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Overall Market Score", f"{last_strategy.overall_market_score:.0f}/100", bias_badge(last_strategy.bias.value))
        col2.metric("Confidence", f"{last_strategy.confidence_score:.0f}/100")
        col3.markdown(f"**Risk Level**\n\n{risk_badge(last_strategy.risk_level.value)}")
        render_bias_gauge(last_strategy.bias_score, width=560)
        st.divider()

    if last_reports:
        st.subheader("Department Reports This Session")
        # Group by asset_or_theme so multiple departments for the same
        # asset appear together, matching how a real research desk would
        # review a name — one asset, every department's read on it.
        by_asset: dict = {}
        for r in last_reports:
            by_asset.setdefault(r.asset_or_theme, []).append(r)

        for asset, reports in by_asset.items():
            with st.container(border=True):
                st.markdown(f"**{asset}**  ·  {len(reports)} department(s)")
                for r in reports:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"{bias_badge(r.bias.value)}  **{r.department}**")
                        st.caption(f"Confidence {r.confidence:.0f}/100 · {risk_badge(r.risk_level.value)}")
                    with c2:
                        render_bias_gauge(r.bias_score, width=320, height=28)

st.divider()
st.subheader("Market Breadth")
st.caption(
    "Computed from whatever PRICE_HISTORY_<TICKER> data is already cached this session (e.g. from "
    "running Chief Risk Fundamentals Officer on Department Reports) — no fresh fetch triggered here. "
    "Running the full weekly cycle (scripts/run_daily_cycle.py --watchlist weekly) populates this "
    "across the whole large-cap universe automatically. See docs/ARCHITECTURE_POSITIONING_SEPARATION.md."
)
manager = get_manager()
price_histories = {}
for key in list(manager._registrations.keys()):
    if not key.startswith("PRICE_HISTORY_"):
        continue
    try:
        ds = manager.get(key)
    except Exception:
        price_histories[key] = []
        continue
    # Every registered key counts toward universe_size regardless of
    # usability — see scripts/run_daily_cycle.py's _print_market_breadth
    # for why pre-filtering to only-usable datasets here would produce a
    # misleading "0 of 0" instead of an honest "0 of N requested."
    price_histories[key] = ds.payload.get("history", []) if ds.is_usable() else []

if not price_histories:
    st.info("No price history cached yet this session — nothing to compute breadth from.")
else:
    breadth = compute_breadth(price_histories)
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Tickers Usable", f"{breadth.usable_count} / {breadth.universe_size}")
    b2.metric(
        "Advance / Decline",
        f"{breadth.advancers} / {breadth.decliners}",
        f"{breadth.advance_decline_ratio}" if breadth.advance_decline_ratio not in (None, float("inf")) else None,
    )
    b3.metric("% Above 50-day SMA", f"{breadth.pct_above_50dma:.0f}%" if breadth.pct_above_50dma is not None else "—")
    b4.metric(f"New Highs / Lows ({breadth.window_days}d window)", f"{breadth.new_highs} / {breadth.new_lows}")

st.divider()
st.subheader("Configuration Status")

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

with st.expander("What's in this dashboard", expanded=False):
    st.markdown(
        """
1. **Data Health** — live status of every registered data source (freshness, quality score, validation)
2. **Department Reports** — run any single-asset Chief Officer live against real data
3. **Strategy Synthesis** — the Chief Strategy Officer's cross-department resolution, including
   the "Explain Every Decision" breakdown
4. **Risk Officer** — build a small portfolio and see concentration/volatility/VaR/drawdown/correlation
5. **Performance & Learning** — historical department/strategy performance from recorded outcomes
6. **Alerts & Execution** — the Chief Execution Officer's gating logic, and (optionally) real Telegram sends
7. **Trade Decision Engine** — Fundamental/Technical/Risk scored independently for trade entry timing
        """
    )

st.divider()
st.caption(
    "This platform never places trades automatically. Every page here reads real data through the "
    "Data Integrity & Refresh Manager (Phase 1), which blocks any analysis on stale, unvalidated, or "
    "missing data rather than fabricating a result."
)
