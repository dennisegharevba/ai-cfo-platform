"""
Strategy Synthesis page — takes whatever's in st.session_state["last_agent_reports"]
(built up on the Department Reports page) and runs the Chief Strategy Officer
over it, showing the full resolved institutional outlook.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import risk_badge, bias_badge, inject_terminal_css, render_bias_gauge, with_broad_context
from agents.chief_strategy_officer import ChiefStrategyOfficer
from agents.institutional_relationship import (
    ExecutionReadiness, EXECUTION_READINESS_BADGES, EXECUTION_READINESS_LABELS,
)

st.set_page_config(page_title="Strategy Synthesis — AI CFO Platform", page_icon="🧭", layout="wide")
inject_terminal_css()
st.title("🧭 Strategy Synthesis")
st.caption("The Chief Strategy Officer resolves every department report into one institutional outlook.")

reports = st.session_state.get("last_agent_reports", [])

# Risk-type reports make a "how risky," not "which direction," claim (see
# agents/chief_strategy_officer.py's synthesize() docstring) — they must
# be routed through the risk_reports parameter, never folded into the
# directional bias average. This mirrors the same split
# scripts/run_daily_cycle.py's run_cycle() already does correctly; this
# dashboard page previously did NOT make this split (a real bug — every
# report was passed into the single directional `reports` parameter,
# meaning a Chief Risk Fundamentals Officer "low volatility" reading could
# silently pull the overall bullish/bearish bias around).
RISK_TYPE_DEPARTMENTS = {"Chief Risk Officer", "Chief Risk Fundamentals Officer"}

if not reports:
    st.info("No department reports in this session yet — go to **Department Reports** and run a few first.")
else:
    asset_names = sorted(set(r.asset_or_theme for r in reports))
    asset = st.selectbox("Synthesize reports for", asset_names)
    matching = with_broad_context(reports, [r for r in reports if r.asset_or_theme == asset])
    directional_matching = [r for r in matching if r.department not in RISK_TYPE_DEPARTMENTS]
    risk_matching = [r for r in matching if r.department in RISK_TYPE_DEPARTMENTS]

    st.caption(
        f"{len(directional_matching)} directional report(s) + {len(risk_matching)} risk report(s) "
        f"will be synthesized for **{asset}** — including the platform's broad Macro/Sentiment reads "
        f"when they've been run this session, not just {asset}-specific departments."
    )
    for r in matching:
        role = " (risk — confirms/warns, never shifts direction)" if r.department in RISK_TYPE_DEPARTMENTS else ""
        st.markdown(f"- **{r.department}**{role}: {r.bias.value} ({r.bias_score:+.1f}), confidence {r.confidence:.0f}, risk {r.risk_level.value}")

    if st.button("Run Chief Strategy Officer", type="primary"):
        officer = ChiefStrategyOfficer()
        result = officer.synthesize(asset, directional_matching, risk_reports=risk_matching)
        st.session_state["last_strategy_report"] = result

    result = st.session_state.get("last_strategy_report")
    if result is not None and result.asset_or_theme == asset:
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Overall Market Score", f"{result.overall_market_score:.0f}/100")
        col2.metric("Confidence Score", f"{result.confidence_score:.0f}/100")
        col3.markdown(f"**Risk Level**\n\n{risk_badge(result.risk_level.value)}")
        col4.markdown(f"**Directional Bias**\n\n{bias_badge(result.bias.value)}")
        render_bias_gauge(result.bias_score, width=700)

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

        if result.decision_explanation:
            with st.expander("Explain This Decision", expanded=False):
                st.markdown(result.decision_explanation)

        if result.committee_table:
            st.subheader("Final Investment Committee")
            import pandas as pd
            table_rows = [
                {
                    "Factor": row["department"],
                    "Bias": row["bias"].replace("_", " ").title(),
                    "Weight": f"{row['weight_pct']:.0f}%",
                    "Confidence": f"{row['confidence']:.0f}%",
                }
                for row in result.committee_table
            ]
            st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Final Market Score", f"{result.overall_market_score:.0f}/100")
            c2.metric("Confidence", f"{result.confidence_score:.0f}%")
            c3.markdown(f"**Recommendation**\n\n{result.committee_recommendation}")

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
