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


def render_score_ring(label: str, value: float, size: int = 120, suffix: str = "") -> None:
    """
    One score as its own circular ring gauge — per an explicit request
    that Fundamental/Technical/Risk/Overall (and similar 0-100 scores)
    each get "their own circles" rather than sharing one shape, or being
    plain st.metric() numbers with no visual read at all.

    `value` is expected on the same 0-100 scale every score this is used
    for already uses (agents.trade_scoring.py's fundamental_score()/
    technical_score()/risk_score()/technical_score() all clamp to 0-100,
    same as models.strategy_report.StrategyReport's overall_market_score/
    confidence_score) — silently clamped here too, defensively, never
    fabricated beyond what's passed in.

    Uses the same PLATFORM_COLORS bearish/neutral/bullish gradient as
    render_bias_gauge, so a low ring and a bearish gauge marker always
    mean the same thing at a glance across every page.
    """
    clamped = max(0.0, min(100.0, value))
    radius = size / 2 - 10
    circumference = 2 * 3.14159265 * radius
    fill_length = circumference * (clamped / 100.0)
    color = (
        PLATFORM_COLORS["bearish"] if clamped < 35
        else PLATFORM_COLORS["bullish"] if clamped > 65
        else PLATFORM_COLORS["neutral"]
    )
    center = size / 2
    font_size = size * 0.22
    svg = f"""
    <div style="text-align:center;">
    <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="{label} {clamped:.0f} of 100">
        <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{PLATFORM_COLORS['panel']}" stroke-width="10" opacity="0.55"/>
        <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{color}" stroke-width="10"
            stroke-dasharray="{fill_length:.1f} {circumference:.1f}" stroke-linecap="round"
            transform="rotate(-90 {center} {center})"/>
        <text x="{center}" y="{center}" text-anchor="middle" dominant-baseline="central"
            font-family="'JetBrains Mono','IBM Plex Mono','SF Mono',Consolas,monospace"
            font-size="{font_size:.0f}" fill="{PLATFORM_COLORS['text']}">{clamped:.0f}{suffix}</text>
    </svg>
    <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em; opacity:0.75; margin-top:-6px;">{label}</div>
    </div>
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
    with col2:
        # Confidence is already 0-100, same scale render_score_ring
        # expects — gets its own circle like every other 0-100 score on
        # the platform now does. Bias Score stays a plain metric + the
        # horizontal gauge below: it's -100..+100 and DIRECTIONAL (which
        # side of zero it's on matters as much as the magnitude), a
        # different shape of information than "how good is this reading,"
        # which is what the ring gauges represent everywhere else.
        render_score_ring("Confidence", report.confidence, size=100)
    col3.markdown(f"**Risk Level**\n\n{risk_badge(report.risk_level.value)}")
    render_bias_gauge(report.bias_score)


# Departments that only ever get run under their own standalone theme name
# (config/watchlist.py's "US Macro Outlook" / "Broad Market Sentiment"
# entries) — never under any individual commodity/FX/equity/crypto asset's
# own name. Matched by DEPARTMENT rather than by hardcoding those theme
# name strings here: a report's department is what
# agents/trade_scoring.py's FUNDAMENTAL_DEPARTMENTS and
# agents/chief_strategy_officer.py actually key off, and staying
# department-keyed means this doesn't silently drift if a theme's display
# name ever changes.
BROAD_CONTEXT_DEPARTMENTS = {"Chief Macro Officer", "Chief Sentiment Officer"}


def with_broad_context(all_reports: list, matching: list) -> list:
    """
    Update, 2026-09-18: a real, confirmed gap — Chief Macro Officer's
    16-factor macro read (CPI/GDP/NFP/Fed policy/etc.) and Chief Sentiment
    Officer's broad market news read were previously only ever synthesized
    under their own standalone "US Macro Outlook"/"Broad Market Sentiment"
    theme entries, never merged into any individual asset's own report set
    — confirmed by a user report that Gold's Trade Decision Engine showed
    no macro/news reasoning at all, only COT positioning and the narrow
    3-factor Commodity Fundamentals read. See scripts/run_daily_cycle.py's
    matching fix for the live scheduled cycle; this is the same fix for
    dashboard pages that build their own `matching` list from whatever's
    in st.session_state["last_agent_reports"].

    Returns `matching` with the most recent Chief Macro Officer / Chief
    Sentiment Officer report from `all_reports` appended, for each of the
    two that isn't already present by department name (so running this on
    the "US Macro Outlook" or "Broad Market Sentiment" asset itself is a
    harmless no-op, not a duplicate). Returns `matching` unchanged if
    neither has been run yet this session — never fabricates one.
    """
    result = list(matching)
    present = {r.department for r in result}
    for dept in BROAD_CONTEXT_DEPARTMENTS:
        if dept in present:
            continue
        candidates = [r for r in all_reports if r.department == dept]
        if candidates:
            result.append(candidates[-1])  # most recently run, if the user re-ran it more than once
    return result

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
