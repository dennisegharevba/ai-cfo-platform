"""
Department Reports page — pick a Chief Officer and run it live against real
data through the shared DataIntegrityManager.

Every report produced here is appended to st.session_state["last_agent_reports"]
so the Strategy Synthesis page (page 3) can pull them straight in.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import get_manager, render_agent_report
from config.settings import FRED_API_KEY, SEC_USER_AGENT, MIN_DATA_QUALITY, NEWS_RSS_URL

from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.yahoo_history_connector import YahooHistoryConnector
from connectors.sec_edgar_connector import SecEdgarConnector
from connectors.binance_connector import BinanceFuturesConnector
from connectors.news_connector import NewsRssConnector

from agents.chief_macro_officer import ChiefMacroOfficer, KEY_CPI, KEY_UNRATE
from agents.chief_bond_strategist import ChiefBondStrategist, KEY_DGS10, KEY_DGS2
from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_fx_analyst import ChiefFXAnalyst
from agents.chief_equity_analyst import ChiefEquityAnalyst
from agents.chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from agents.chief_sentiment_officer import ChiefSentimentOfficer
from agents.chief_technical_officer import ChiefTechnicalOfficer

st.set_page_config(page_title="Department Reports — AI CFO Platform", page_icon="🏛️", layout="wide")
st.title("🏛️ Department Reports")
st.caption("Run any single-asset Chief Officer live. Each run is added to this session's synthesis pool.")

manager = get_manager()

if "last_agent_reports" not in st.session_state:
    st.session_state["last_agent_reports"] = []

DEPARTMENTS = [
    "Chief Macro Officer",
    "Chief Bond Strategist",
    "Chief Commodity Analyst",
    "Chief FX Analyst",
    "Chief Equity Analyst",
    "Chief Cryptocurrency Analyst",
    "Chief Sentiment Officer",
    "Chief Technical Officer",
]

department = st.selectbox("Department", DEPARTMENTS)
report = None

if department == "Chief Macro Officer":
    st.caption("Uses US CPI + unemployment rate (FRED). No input needed.")
    if st.button("Run Chief Macro Officer", type="primary"):
        if not manager.is_registered(KEY_CPI):
            manager.register(KEY_CPI, primary=FredConnector(series_id="CPIAUCSL", api_key=FRED_API_KEY))
        if not manager.is_registered(KEY_UNRATE):
            manager.register(KEY_UNRATE, primary=FredConnector(series_id="UNRATE", api_key=FRED_API_KEY))
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

elif department == "Chief FX Analyst":
    market_name = st.text_input("CFTC market name", value="EURO FX - CHICAGO MERCANTILE EXCHANGE")
    theme = st.text_input("Display name", value="EUR/USD")
    if st.button("Run Chief FX Analyst", type="primary"):
        key = f"COT_{market_name}"
        if not manager.is_registered(key):
            manager.register(key, primary=CotConnector(market_name, weeks_history=8))
        report = ChiefFXAnalyst(manager, cot_key=key, min_quality=MIN_DATA_QUALITY).analyze(theme)

elif department == "Chief Equity Analyst":
    cik = st.text_input("SEC CIK (e.g. Apple = 320193)", value="320193")
    ticker = st.text_input("Display ticker", value="AAPL")
    if st.button("Run Chief Equity Analyst", type="primary"):
        eps_key, rev_key = f"SEC_{ticker}_EPS", f"SEC_{ticker}_REV"
        if not manager.is_registered(eps_key):
            manager.register(eps_key, primary=SecEdgarConnector(cik=cik, concept="EarningsPerShareDiluted", user_agent=SEC_USER_AGENT))
        if not manager.is_registered(rev_key):
            manager.register(rev_key, primary=SecEdgarConnector(cik=cik, concept="Revenues", user_agent=SEC_USER_AGENT))
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

elif department == "Chief Technical Officer":
    ticker = st.text_input("Ticker", value="SPY")
    if st.button("Run Chief Technical Officer", type="primary"):
        key = f"PRICE_HISTORY_{ticker}"
        if not manager.is_registered(key):
            manager.register(key, primary=YahooHistoryConnector(ticker, period="6mo", interval="1d"))
        report = ChiefTechnicalOfficer(manager, price_key=key, min_quality=MIN_DATA_QUALITY).analyze(ticker)

if report is not None:
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
