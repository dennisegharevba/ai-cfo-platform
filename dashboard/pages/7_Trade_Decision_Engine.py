"""
Institutional Trade Decision Engine page — runs the Chief Trade Decision
Officer over whatever's in st.session_state["last_agent_reports"] (same
source the Strategy Synthesis page uses), and additionally lets the user
open/close a trade for lifecycle tracking (spec sections 4 and 7).

Deliberately a SEPARATE page from Strategy Synthesis, not a replacement —
per spec section 1, this engine's whole point is that Fundamental/
Technical/Risk stay visibly separate here, rather than being read off the
Chief Strategy Officer's single overall_market_score.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import (
    get_report_store, risk_badge, momentum_badge, trade_health_badge,
)
from agents.chief_trade_decision_officer import ChiefTradeDecisionOfficer
from models.open_trade import OpenTrade, TradeDirection
from models.trade_decision import EXECUTION_RATING_LABELS


def _fmt(value):
    if value is None:
        return "n/a"
    return f"{value:+.0f}"


def _risk_label(risk_score_value: float) -> str:
    if risk_score_value >= 75:
        return "low"
    if risk_score_value >= 55:
        return "moderate"
    if risk_score_value >= 30:
        return "elevated"
    return "high"


st.set_page_config(page_title="Trade Decision Engine — AI CFO Platform", page_icon="🏛️", layout="wide")
st.title("🏛️ Institutional Trade Decision Engine")
st.caption(
    "Fundamental, Technical, and Risk are scored independently and never collapsed into one number "
    "before an execution decision is made — see the Core Principle in the platform's upgrade spec."
)

reports = st.session_state.get("last_agent_reports", [])

if not reports:
    st.info("No department reports in this session yet — go to **Department Reports** and run a few first.")
else:
    asset_names = sorted(set(r.asset_or_theme for r in reports))
    asset = st.selectbox("Run the Trade Decision Engine for", asset_names)
    matching = [r for r in reports if r.asset_or_theme == asset]

    st.caption(f"{len(matching)} report(s) available for **{asset}**.")
    with st.expander("Contributing department reports", expanded=False):
        for r in matching:
            st.markdown(f"- **{r.department}**: {r.bias.value} ({r.bias_score:+.1f}), confidence {r.confidence:.0f}, risk {r.risk_level.value}")

    store = get_report_store()

    if st.button("Run Chief Trade Decision Officer", type="primary"):
        officer = ChiefTradeDecisionOfficer(report_store=store)
        st.session_state["last_trade_decision"] = officer.decide(asset, matching)

    decision = st.session_state.get("last_trade_decision")
    if decision is not None and decision.asset_or_theme == asset:
        st.divider()

        # --- Section 1-2: the three independent scores + overall blend ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fundamental Score (40%)", f"{decision.fundamental_score:.0f}/100")
        c2.metric("Technical Score (40%)", f"{decision.technical_score:.0f}/100")
        c3.metric("Risk Score (20%)", f"{decision.risk_score:.0f}/100", help="Higher = LOWER risk")
        c4.metric("Overall Score", f"{decision.overall_score:.0f}/100")

        # --- Section 3: score momentum ---
        st.subheader("Score Momentum")
        m1, m2, m3, m4 = st.columns(4)
        for col, label, momentum in (
            (m1, "Fundamental", decision.fundamental_momentum),
            (m2, "Technical", decision.technical_momentum),
            (m3, "Risk", decision.risk_momentum),
            (m4, "Overall", decision.overall_momentum),
        ):
            with col:
                st.markdown(f"**{label}**")
                st.markdown(momentum_badge(momentum.momentum.value))
                if momentum.previous_score is not None:
                    st.caption(f"prev {momentum.previous_score:.0f} · 1h {_fmt(momentum.change_1h)} · 24h {_fmt(momentum.change_24h)} · wk {_fmt(momentum.change_weekly)}")
                if momentum.explanation:
                    st.caption("Why: " + "; ".join(momentum.explanation))

        st.divider()

        # --- Section 5-6: execution rating + trade grade ---
        e1, e2, e3 = st.columns(3)
        e1.markdown(f"**Execution Status**\n\n### {EXECUTION_RATING_LABELS[decision.execution_rating]}")
        e2.markdown(f"**Institutional Trade Grade**\n\n### {decision.trade_grade.value}")
        e3.markdown(f"**Risk**\n\n{risk_badge(_risk_label(decision.risk_score))}")

        # --- Section 8: entry confirmation checklist ---
        st.subheader("Entry Confirmation Checklist")
        checks = decision.entry_confirmation
        check_cols = st.columns(4)
        labels = [
            ("Trend alignment", checks.trend_alignment), ("Market structure", checks.market_structure_confirmed),
            ("Breakout", checks.breakout_confirmed), ("Volume", checks.volume_confirmed),
            ("Liquidity", checks.liquidity_confirmed), ("Macro alignment", checks.macro_alignment),
            ("Risk acceptable", checks.risk_acceptable), ("Min. R:R", checks.minimum_rr_achieved),
        ]
        for i, (label, passed) in enumerate(labels):
            check_cols[i % 4].markdown(f"{'✅' if passed else '❌'} {label}")
        if checks.notes:
            with st.expander("Why any unchecked items failed", expanded=False):
                for n in checks.notes:
                    st.markdown(f"- {n}")

        # --- Section 9: decision explanation ---
        st.subheader("Institutional Explanation")
        st.markdown(decision.decision_explanation)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Key Catalysts**")
            for c in decision.key_catalysts:
                st.markdown(f"- {c}")
        with col_b:
            st.markdown("**Key Risks**")
            for r in decision.key_risks:
                st.markdown(f"- {r}")

        st.caption(
            f"Contributing: {', '.join(decision.contributing_departments) or 'none'} · "
            f"Excluded: {', '.join(decision.excluded_departments) or 'none'}"
        )

        # --- Section 4 & 7: trade lifecycle / position management ---
        st.divider()
        st.subheader("Position Management")

        open_row = store.get_open_trade(asset)
        if open_row is None:
            st.markdown(f"No open trade recorded for **{asset}**.")
            with st.form("open_trade_form"):
                st.markdown(f"Record a trade you've actually taken on **{asset}**, so this desk can monitor it structurally rather than just watching the Overall Score.")
                direction = st.radio("Direction", ["long", "short"], horizontal=True)
                entry_price = st.number_input("Entry price (optional)", value=0.0, step=0.01)
                stop_loss = st.number_input("Stop-loss level (optional)", value=0.0, step=0.01)
                structure_note = st.text_input("Entry market structure note", value="")
                submitted = st.form_submit_button("Open Trade")
                if submitted:
                    store.open_trade(OpenTrade(
                        id=None, asset_or_theme=asset, direction=TradeDirection(direction),
                        entry_technical_bias_score=decision.technical_score,
                        entry_fundamental_bias_score=decision.fundamental_score,
                        entry_risk_score=decision.risk_score,
                        entry_market_structure_note=structure_note,
                        stop_loss_level=stop_loss or None,
                        entry_price=entry_price or None,
                    ))
                    st.success(f"Trade opened on {asset}. Re-run the Trade Decision Officer to see lifecycle status.")
                    st.rerun()
        else:
            h1, h2 = st.columns(2)
            h1.markdown(f"**Trade Health**\n\n{trade_health_badge(decision.trade_health.value)}")
            h2.markdown(f"**Institutional Conviction**\n\n{decision.institutional_conviction or 'n/a'}")
            st.caption(f"Opened {open_row['opened_at']} · direction {open_row['direction']} · entry structure: {open_row['entry_market_structure_note']}")
            if st.button("Close Trade"):
                store.close_trade(open_row["id"], close_reason="Manually closed from dashboard")
                st.success("Trade closed.")
                st.rerun()
