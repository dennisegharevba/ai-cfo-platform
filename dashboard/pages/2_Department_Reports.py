"""
Department Reports page — pick a Chief Officer and run it live against real
data through the shared DataIntegrityManager.

Every report produced here is appended to st.session_state["last_agent_reports"]
so the Strategy Synthesis page (page 3) can pull them straight in.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import get_manager, render_agent_report, inject_terminal_css, get_report_store
from agents.news_digest import build_weekly_sentiment_digest
from config.settings import FRED_API_KEY, SEC_USER_AGENT, MIN_DATA_QUALITY, NEWS_RSS_URL, EIA_API_KEY

from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.sec_edgar_connector import SecEdgarConnector, REVENUE_FALLBACK_CONCEPTS
from connectors.sec_ticker_lookup import resolve_cik
from connectors.binance_connector import BinanceFuturesConnector
from connectors.news_connector import NewsRssConnector
from connectors.yahoo_history_connector import YahooHistoryConnector

from agents.chief_macro_officer import ChiefMacroOfficer, register_macro_data_sources
from agents.chief_bond_strategist import ChiefBondStrategist, KEY_DGS10, KEY_DGS2
from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_commodity_fundamentals_officer import (
    ChiefCommodityFundamentalsOfficer, register_commodity_fundamentals_sources,
)
from agents.chief_fx_analyst import ChiefFXAnalyst
from agents.chief_equity_analyst import ChiefEquityAnalyst
from agents.chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from agents.chief_sentiment_officer import ChiefSentimentOfficer
from agents.chief_seasonality_officer import ChiefSeasonalityOfficer
from agents.chief_risk_fundamentals_officer import ChiefRiskFundamentalsOfficer

st.set_page_config(page_title="Department Reports — AI CFO Platform", page_icon="🏛️", layout="wide")
inject_terminal_css()
st.title("🏛️ Department Reports")
st.caption("Run any single-asset Chief Officer live. Each run is added to this session's synthesis pool.")

manager = get_manager()

if "last_agent_reports" not in st.session_state:
    st.session_state["last_agent_reports"] = []

DEPARTMENTS = [
    "Chief Macro Officer",
    "Chief Bond Strategist",
    "Chief Commodity Analyst",
    "Chief Commodity Fundamentals Officer",
    "Chief FX Analyst",
    "Chief Equity Analyst",
    "Chief Cryptocurrency Analyst",
    "Chief Sentiment Officer",
    "Chief Seasonality Officer",
    "Chief Risk Fundamentals Officer",
]

department = st.selectbox("Department", DEPARTMENTS)
report = None

if department == "Chief Macro Officer":
    st.caption("Uses 16 real FRED-backed macroeconomic factors (CPI, Core CPI, PPI, Core PCE, GDP, "
               "Retail Sales, labor market, credit spreads, and more). No input needed.")
    if st.button("Run Chief Macro Officer", type="primary"):
        register_macro_data_sources(manager, fred_api_key=FRED_API_KEY)
        report = ChiefMacroOfficer(manager, min_quality=MIN_DATA_QUALITY).analyze("US Macro Outlook")

elif department == "Chief Bond Strategist":
    st.caption("Uses 10Y + 2Y US Treasury yields (FRED). No input needed.")
    if st.button("Run Chief Bond Strategist", type="primary"):
        if not manager.is_registered(KEY_DGS10):
            manager.register(KEY_DGS10, primary=FredConnector(series_id="DGS10", api_key=FRED_API_KEY))
        if not manager.is_registered(KEY_DGS2):
            manager.register(KEY_DGS2, primary=FredConnector(series_id="DGS2", api_key=FRED_API_KEY))
        report = ChiefBondStrategist(manager, min_quality=MIN_DATA_QUALITY).analyze("US Treasuries")

elif department == "Chief Commodity Analyst":
    market_name = st.text_input("CFTC market name", value="GOLD - COMMODITY EXCHANGE INC.")
    theme = st.text_input("Display name", value="Gold")
    if st.button("Run Chief Commodity Analyst", type="primary"):
        key = f"COT_{market_name}"
        if not manager.is_registered(key):
            manager.register(key, primary=CotConnector(market_name, weeks_history=8))
        report = ChiefCommodityAnalyst(manager, cot_key=key, min_quality=MIN_DATA_QUALITY).analyze(theme)

elif department == "Chief Commodity Fundamentals Officer":
    theme = st.text_input(
        "Commodity (Crude Oil, Natural Gas, Gold, Silver, Platinum, Palladium have configured factors)",
        value="Crude Oil",
    )
    st.caption(
        "Energy commodities use the free EIA API for supply/demand data. Gold/Silver/Platinum/"
        "Palladium are fundamentally backed by US Dollar-related data (real yields, Dollar Index, "
        "Fed Funds Rate) — the same fundamentals driving USD, since these metals are dollar-priced. "
        "Other commodities (Copper, agriculture) have no free structured fundamentals source "
        "connected yet and will honestly report zero confidence — see "
        "docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md."
    )
    if st.button("Run Chief Commodity Fundamentals Officer", type="primary"):
        register_commodity_fundamentals_sources(manager, theme, eia_api_key=EIA_API_KEY)
        register_macro_data_sources(manager, fred_api_key=FRED_API_KEY)  # needed for precious metals' shared USD factors
        report = ChiefCommodityFundamentalsOfficer(manager, commodity=theme, min_quality=MIN_DATA_QUALITY).analyze(theme)

elif department == "Chief FX Analyst":
    market_name = st.text_input("CFTC market name", value="EURO FX - CHICAGO MERCANTILE EXCHANGE")
    theme = st.text_input("Display name", value="EUR/USD")
    if st.button("Run Chief FX Analyst", type="primary"):
        key = f"COT_{market_name}"
        if not manager.is_registered(key):
            manager.register(key, primary=CotConnector(market_name, weeks_history=8))
        report = ChiefFXAnalyst(manager, cot_key=key, min_quality=MIN_DATA_QUALITY).analyze(theme)

elif department == "Chief Equity Analyst":
    ticker = st.text_input("Ticker (CIK is resolved automatically)", value="AAPL")
    if st.button("Run Chief Equity Analyst", type="primary"):
        cik = resolve_cik(manager, ticker, user_agent=SEC_USER_AGENT)
        if cik is None:
            st.error(f"Couldn't resolve a CIK for '{ticker}' — check the ticker, or SEC's mapping service may be unreachable.")
        else:
            eps_key, rev_key = f"SEC_{ticker}_EPS", f"SEC_{ticker}_REV"
            if not manager.is_registered(eps_key):
                manager.register(eps_key, primary=SecEdgarConnector(cik=cik, concept="EarningsPerShareDiluted", user_agent=SEC_USER_AGENT))
            if not manager.is_registered(rev_key):
                manager.register(rev_key, primary=SecEdgarConnector(
                    cik=cik, concept="Revenues", user_agent=SEC_USER_AGENT, fallback_concepts=REVENUE_FALLBACK_CONCEPTS,
                ))
            report = ChiefEquityAnalyst(manager, eps_key=eps_key, revenue_key=rev_key, min_quality=MIN_DATA_QUALITY).analyze(ticker)

elif department == "Chief Cryptocurrency Analyst":
    symbol = st.text_input("Binance futures symbol", value="BTCUSDT")
    if st.button("Run Chief Cryptocurrency Analyst", type="primary"):
        key = f"CRYPTO_{symbol}"
        if not manager.is_registered(key):
            manager.register(key, primary=BinanceFuturesConnector(symbol, history_limit=30))
        report = ChiefCryptocurrencyAnalyst(manager, crypto_key=key, min_quality=MIN_DATA_QUALITY).analyze(symbol)

elif department == "Chief Sentiment Officer":
    st.caption("Uses the configured market-news RSS feed.")
    if st.button("Run Chief Sentiment Officer", type="primary"):
        key = "MARKET_NEWS"
        if not manager.is_registered(key):
            manager.register(key, primary=NewsRssConnector(NEWS_RSS_URL))
        report = ChiefSentimentOfficer(manager, news_key=key, min_quality=MIN_DATA_QUALITY).analyze("Broad Market Sentiment")

    st.divider()
    st.subheader("📰 Weekly Digest")
    st.caption(
        "Aggregates the last 7 days of saved Chief Sentiment Officer reports — see "
        "docs/ARCHITECTURE_WEEKLY_DIGEST.md. Reports accumulate over time from "
        "scheduled runs (e.g. .github/workflows/scheduled_run.yml) or scripts/run_daily_cycle.py "
        "writing to this same database; a single interactive run above doesn't add much history "
        "on its own."
    )
    since_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    store = get_report_store()
    week_reports = store.get_agent_reports(department="Chief Sentiment Officer", since=since_cutoff, limit=500)
    digest = build_weekly_sentiment_digest(week_reports)
    if digest is None:
        st.info(
            "No saved Chief Sentiment Officer reports in the last 7 days yet — the digest will "
            "populate once reports have been recorded over time (see caption above)."
        )
    else:
        dcol1, dcol2, dcol3 = st.columns(3)
        dcol1.metric("Reports this week", digest.report_count)
        dcol2.metric("Average bias score", f"{digest.average_bias_score:+.1f}")
        dcol3.metric("Average confidence", f"{digest.average_confidence:.0f}")
        st.caption(f"Window: {digest.date_range_start} to {digest.date_range_end}")
        st.write("**Bias day counts:**", digest.bias_day_counts)
        if digest.top_catalysts:
            st.write("**Most-repeated catalysts this week:**")
            for c in digest.top_catalysts:
                st.markdown(f"- {c}")
        if digest.top_risks:
            st.write("**Most-repeated risks this week:**")
            for r in digest.top_risks:
                st.markdown(f"- {r}")

elif department == "Chief Seasonality Officer":
    theme = st.text_input(
        "Asset (Gold, WTI Crude Oil, Natural Gas, Corn, Wheat, Soybeans, S&P500, NASDAQ100 have configured patterns)",
        value="Gold",
    )
    st.caption(
        "Uses well-documented historical seasonal patterns — NOT a live statistical backtest this "
        "platform computed. No data fetch needed (calendar-based). See "
        "docs/ARCHITECTURE_REMAINING_CATEGORIES.md."
    )
    if st.button("Run Chief Seasonality Officer", type="primary"):
        report = ChiefSeasonalityOfficer().analyze(theme)

elif department == "Chief Risk Fundamentals Officer":
    theme = st.text_input("Display name", value="Gold")
    ticker = st.text_input("Yahoo Finance ticker (e.g. GC=F for gold futures, AAPL for Apple)", value="GC=F")
    st.caption(
        "Computes real annualized volatility and maximum drawdown from free Yahoo Finance price "
        "history — the same tested math the portfolio-level Chief Risk Officer uses."
    )
    if st.button("Run Chief Risk Fundamentals Officer", type="primary"):
        key = f"PRICE_HISTORY_{ticker}"
        if not manager.is_registered(key):
            manager.register(key, primary=YahooHistoryConnector(ticker, period="6mo", interval="1d"))
        report = ChiefRiskFundamentalsOfficer(manager, ticker=ticker, min_quality=MIN_DATA_QUALITY).analyze(theme)

if report is not None:
    # Replace any EXISTING report for this same (department, asset) pair
    # rather than blindly appending — found via live testing to matter:
    # re-running a department (a completely natural workflow — re-checking
    # data, re-testing after a fix) silently left BOTH the old and new
    # report sitting in the pool together. Strategy Synthesis and the
    # Trade Decision Engine both pass this whole pool straight into their
    # weighted-average logic with no deduplication of their own, so a
    # duplicated department was silently getting DOUBLE-WEIGHTED in the
    # final result — not just a cosmetic duplicate in the list.
    st.session_state["last_agent_reports"] = [
        r for r in st.session_state["last_agent_reports"]
        if not (r.department == report.department and r.asset_or_theme == report.asset_or_theme)
    ]
    st.session_state["last_agent_reports"].append(report)
    st.divider()
    st.subheader(f"{report.department}: {report.asset_or_theme}")
    render_agent_report(report)

if st.session_state["last_agent_reports"]:
    st.divider()
    st.subheader(f"This session's report pool ({len(st.session_state['last_agent_reports'])})")
    for r in st.session_state["last_agent_reports"]:
        st.markdown(f"- **{r.department}** — {r.asset_or_theme}: {r.bias.value} ({r.bias_score:+.1f}), confidence {r.confidence:.0f}")
    if st.button("Clear report pool"):
        st.session_state["last_agent_reports"] = []
        st.rerun()
