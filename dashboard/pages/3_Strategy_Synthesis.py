"""
Strategy Synthesis page — takes whatever's in st.session_state["last_agent_reports"]
(built up on the Department Reports page) and runs the Chief Strategy Officer
over it, showing the full resolved institutional outlook.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import risk_badge, bias_badge
from agents.chief_strategy_officer import ChiefStrategyOfficer
from agents.institutional_relationship import (
    ExecutionReadiness, EXECUTION_READINESS_BADGES, EXECUTION_READINESS_LABELS,
)

st.set_page_config(page_title="Strategy Synthesis — AI CFO Platform", page_icon="🧭", layout="wide")
st.title("🧭 Strategy Synthesis")
st.caption("The Chief Strategy Officer resolves every department report into one institutional outlook.")

reports = st.session_state.get("last_agent_reports", [])

if not reports:
    st.info("No department reports in this session yet — go to **Department Reports** and run a few first.")
else:
    asset_names = sorted(set(r.asset_or_theme for r in reports))
    asset = st.selectbox("Synthesize reports for", asset_names)
    matching = [r for r in reports if r.asset_or_theme == asset]

    st.caption(f"{len(matching)} report(s) will be synthesized for **{asset}**.")
    for r in matching:
        st.markdown(f"- **{r.department}**: {r.bias.value} ({r.bias_score:+.1f}), confidence {r.confidence:.0f}, risk {r.risk_level.value}")

    if st.button("Run Chief Strategy Officer", type="primary"):
        officer = ChiefStrategyOfficer()
        result = officer.synthesize(asset, matching)
        st.session_state["last_strategy_report"] = result

    result = st.session_state.get("last_strategy_report")
    if result is not None and result.asset_or_theme == asset:
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Overall Market Score", f"{result.overall_market_score:.0f}/100")
        col2.metric("Confidence Score", f"{result.confidence_score:.0f}/100")
        col3.markdown(f"**Risk Level**\n\n{risk_badge(result.risk_level.value)}")
        col4.markdown(f"**Directional Bias**\n\n{bias_badge(result.bias.value)}")

        if result.execution_readiness:
            try:
                readiness = ExecutionReadiness(result.execution_readiness)
                badge = EXECUTION_READINESS_BADGES[readiness]
                label = EXECUTION_READINESS_LABELS[readiness]
                st.markdown(f"### Execution Readiness: {badge} {label}")
            except ValueError:
                pass  # unrecognized value (e.g. an older stored record) — skip rather than crash

        if result.institutional_commentary:
            st.subheader("Institutional Commentary")
            st.markdown(result.institutional_commentary)

        st.subheader("Trade Thesis")
        st.markdown(result.trade_thesis)

        st.subheader("Investment Committee Summary")
        st.markdown(result.investment_committee_summary)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Catalysts**")
            for c in result.catalysts:
                st.markdown(f"- {c}")
        with col_b:
            st.markdown("**Risks**")
            for r in result.risks:
                st.markdown(f"- {r}")

        if result.invalidation_notes:
            st.markdown("**Invalidation Notes** _(qualitative — see docs/ARCHITECTURE_PHASE7.md)_")
            for n in result.invalidation_notes:
                st.markdown(f"- {n}")

        st.caption(
            f"Contributing: {', '.join(result.contributing_departments) or 'none'} · "
            f"Excluded: {', '.join(result.excluded_departments) or 'none'}"
        )
