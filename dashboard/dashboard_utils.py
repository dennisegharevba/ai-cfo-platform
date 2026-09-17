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
import uuid
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

# --- Visual identity ---
# Named palette for the platform's dark-terminal design (see
# .streamlit/config.toml for the full rationale). Kept here as the single
# source of truth so the gauge component and any future custom-styled
# element draw from the same values as the theme config, rather than
# duplicating hex codes in two places.
PLATFORM_COLORS = {
    "background": "#0B0E14",
    "panel": "#131722",
    "accent_gold": "#C9A227",
    "bullish": "#3FB950",
    "bearish": "#F85149",
    "neutral": "#7D8590",
    "text": "#E6E8EB",
    "text_muted": "#7D8590",
}


def inject_terminal_css() -> None:
    """
    Small, targeted CSS additions on top of the .streamlit/config.toml
    theme — NOT a full framework override (Streamlit's own theme system
    already handles the base colors; this only adds what the theme config
    can't: a monospace treatment for numeric/data values, so scores and
    prices read as data rather than prose, which is a genuine structural
    signal for a terminal-style interface, not decoration). Call once per
    page, near the top, after st.set_page_config().
    """
    st.markdown(
        """
        <style>
        /* Tabular, monospace treatment for metric values — numbers are
           numbers, distinct from labels/prose, the same convention real
           trading terminals use. */
        div[data-testid="stMetricValue"] {
            font-family: "JetBrains Mono", "IBM Plex Mono", "SF Mono", Consolas, monospace;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.02em;
        }
        div[data-testid="stMetricLabel"] {
            text-transform: uppercase;
            font-size: 0.72rem;
            letter-spacing: 0.06em;
            opacity: 0.75;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_bias_gauge(bias_score: float, width: int = 280, height: int = 34) -> None:
    """
    The platform's signature visual element: a horizontal -100..+100
    gauge with a marker at the current bias_score, color-graded from
    bearish red through neutral gray to bullish green. Chosen as the
    signature specifically because bias_score on this exact -100..+100
    scale is the one value every single agent in this platform produces
    (Macro, Commodity Fundamentals, COT, Sentiment, Seasonality, Risk,
    and the overall Strategy Officer synthesis all share it) — a visual
    identity drawn directly from the platform's real, actual data model,
    not a decorative addition.

    Renders directly (calls st.markdown itself) rather than returning a
    string, so every call site gets identical, tested rendering behavior.
    """
    clamped = max(-100.0, min(100.0, bias_score))
    x = ((clamped + 100.0) / 200.0) * width
    marker_color = (
        PLATFORM_COLORS["bearish"] if clamped < -15
        else PLATFORM_COLORS["bullish"] if clamped > 15
        else PLATFORM_COLORS["neutral"]
    )
    mid = height / 2
    # A proper unique ID per gauge instance — needed because SVG gradient
    # IDs must be unique within the page's DOM, and this component can be
    # called multiple times on one page (e.g. a grid of asset cards).
    # id(bias_score) would NOT be safe here: it's object identity, not a
    # stable unique value, and small/duplicate float objects can share
    # identities in CPython — a real bug caught before it shipped.
    gradient_id = f"gauge-{uuid.uuid4().hex[:8]}"
    svg = f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Bias score {clamped:+.1f} of a possible -100 to +100">
        <defs>
            <linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="{PLATFORM_COLORS['bearish']}"/>
                <stop offset="50%" stop-color="{PLATFORM_COLORS['neutral']}"/>
                <stop offset="100%" stop-color="{PLATFORM_COLORS['bullish']}"/>
            </linearGradient>
        </defs>
        <rect x="0" y="{mid - 3}" width="{width}" height="6" rx="3" fill="url(#{gradient_id})" opacity="0.30"/>
        <line x1="{width/2:.1f}" y1="2" x2="{width/2:.1f}" y2="{height - 2}" stroke="{PLATFORM_COLORS['text_muted']}" stroke-width="1" stroke-dasharray="2,2"/>
        <circle cx="{x:.1f}" cy="{mid}" r="6" fill="{marker_color}" stroke="{PLATFORM_COLORS['background']}" stroke-width="2"/>
    </svg>
    """
    st.markdown(svg, unsafe_allow_html=True)


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


MOMENTUM_COLORS = {
    "strengthening": "🟢",
    "stable": "⚪",
    "weakening": "🟠",
    "major_deterioration": "🔴",
    "insufficient_history": "⚫",
}

TRADE_HEALTH_COLORS = {
    "excellent": "🟢",
    "healthy": "🟢",
    "weakening": "🟠",
    "critical": "🔴",
    "not_open": "⚪",
}


def momentum_badge(momentum_value: str) -> str:
    return f"{MOMENTUM_COLORS.get(momentum_value, '⚪')} {momentum_value.replace('_', ' ').title()}"


def trade_health_badge(trade_health_value: str) -> str:
    return f"{TRADE_HEALTH_COLORS.get(trade_health_value, '⚪')} {trade_health_value.replace('_', ' ').title()}"


def get_report_store() -> ReportStore:
    """
    One shared ReportStore per dashboard session, backed by the same
    on-disk file get_learning_officer() already uses — so trade_decisions
    and open_trades rows persist across dashboard restarts, and so this
    store sees the exact same agent_reports/strategy_reports history the
    rest of the platform is already writing to.
    """
    if "report_store" not in st.session_state:
        st.session_state["report_store"] = ReportStore("ai_cfo_platform.db")
    return st.session_state["report_store"]


def render_agent_report(report) -> None:
    """Render one AgentReport as a compact Streamlit card."""
    col1, col2, col3 = st.columns(3)
    col1.metric("Bias Score", f"{report.bias_score:+.1f}", bias_badge(report.bias.value))
    col2.metric("Confidence", f"{report.confidence:.0f}/100")
    col3.markdown(f"**Risk Level**\n\n{risk_badge(report.risk_level.value)}")
    render_bias_gauge(report.bias_score)

    if report.factor_breakdown:
        with st.expander(f"Factor breakdown ({len(report.factor_breakdown)} factors)", expanded=True):
            import pandas as pd
            rows = [{
                "Factor": f.name,
                "Bias": f.bias.value,
                "Score": f"{f.score:+.1f}",
                "Weight (1-10)": f.importance_weight,
                "Confidence": f"{f.confidence:.0f}",
                "Current": f.current_value,
                "Previous": f.previous_value,
                "Source": f.source,
                "Updated": f.last_updated.date().isoformat(),
            } for f in report.factor_breakdown]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

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
