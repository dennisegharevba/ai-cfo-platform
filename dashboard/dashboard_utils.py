"""
Shared helpers for the Streamlit dashboard pages.

Session-state keys used across pages (documented here since Streamlit
multipage apps share one session_state across all pages):
    "manager"           -> core.DataIntegrityManager (one shared instance)
    "last_agent_reports" -> list of models.report.AgentReport, most recent
                            department run(s) from the Department Reports page
    "last_strategy_report" -> models.strategy_report.StrategyReport | None
    "learning_officer"  -> agents.chief_learning_officer.ChiefLearningOfficer
                           (backed by a real on-disk SQLite file, not :memory:,
                           so it survives across dashboard reruns/restarts)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable regardless of Streamlit's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from core.refresh_manager import DataIntegrityManager
from agents.chief_learning_officer import ChiefLearningOfficer
from database.report_store import ReportStore
from config.settings import MIN_DATA_QUALITY

RISK_COLORS = {
    "low": "🟢",
    "moderate": "🟡",
    "elevated": "🟠",
    "high": "🔴",
}

BIAS_COLORS = {
    "strongly_bullish": "🟢🟢",
    "bullish": "🟢",
    "neutral": "⚪",
    "bearish": "🔴",
    "strongly_bearish": "🔴🔴",
}


def get_manager() -> DataIntegrityManager:
    """One shared DataIntegrityManager per dashboard session, so caching
    across pages actually means something (a re-fetch on page 2 doesn't
    throw away what page 1 already validated)."""
    if "manager" not in st.session_state:
        st.session_state["manager"] = DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)
    return st.session_state["manager"]


def get_learning_officer() -> ChiefLearningOfficer:
    """Backed by a real file (not :memory:) so recorded history survives
    across dashboard restarts, not just across reruns within one session."""
    if "learning_officer" not in st.session_state:
        st.session_state["learning_officer"] = ChiefLearningOfficer(store=ReportStore("ai_cfo_platform.db"))
    return st.session_state["learning_officer"]


def risk_badge(risk_level_value: str) -> str:
    return f"{RISK_COLORS.get(risk_level_value, '⚪')} {risk_level_value.upper()}"


def bias_badge(bias_value: str) -> str:
    return f"{BIAS_COLORS.get(bias_value, '⚪')} {bias_value.replace('_', ' ').title()}"


def render_agent_report(report) -> None:
    """Render one AgentReport as a compact Streamlit card."""
    col1, col2, col3 = st.columns(3)
    col1.metric("Bias Score", f"{report.bias_score:+.1f}", bias_badge(report.bias.value))
    col2.metric("Confidence", f"{report.confidence:.0f}/100")
    col3.markdown(f"**Risk Level**\n\n{risk_badge(report.risk_level.value)}")

    if report.evidence:
        with st.expander("Evidence", expanded=False):
            for e in report.evidence:
                st.markdown(f"- {e}")
    if report.catalysts:
        with st.expander("Catalysts", expanded=False):
            for c in report.catalysts:
                st.markdown(f"- {c}")
    if report.risks:
        with st.expander("Risks", expanded=False):
            for r in report.risks:
                st.markdown(f"- {r}")
    if report.data_gaps:
        st.warning("Data gaps (excluded from this analysis): " + "; ".join(report.data_gaps))
