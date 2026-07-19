"""
Data Health page — registers a representative set of real connectors from
every phase and shows the Data Integrity & Refresh Manager's live status
report (freshness, quality score, validation status per dataset).

This is the dashboard's most direct surface of Phase 1's core promise:
never analyze stale/unvalidated/missing data. A red "not usable" row here
is the correct, honest result when a source is unreachable — not a bug.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.dashboard_utils import get_manager
from config.settings import FRED_API_KEY, SEC_USER_AGENT, NEWS_RSS_URL
from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.yahoo_connector import YahooConnector
from connectors.yahoo_history_connector import YahooHistoryConnector
from connectors.sec_edgar_connector import SecEdgarConnector
from connectors.binance_connector import BinanceFuturesConnector
from connectors.news_connector import NewsRssConnector

st.set_page_config(page_title="Data Health — AI CFO Platform", page_icon="🩺", layout="wide")
st.title("🩺 Data Health")
st.caption("Live status from the Data Integrity & Refresh Manager (Phase 1).")

manager = get_manager()

REGISTRATIONS = {
    "FRED_CPI": lambda: FredConnector(series_id="CPIAUCSL", api_key=FRED_API_KEY),
    "FRED_UNRATE": lambda: FredConnector(series_id="UNRATE", api_key=FRED_API_KEY),
    "FRED_DGS10": lambda: FredConnector(series_id="DGS10", api_key=FRED_API_KEY),
    "COT_GOLD": lambda: CotConnector("GOLD - COMMODITY EXCHANGE INC.", weeks_history=8),
    "PRICE_SPY": lambda: YahooConnector("SPY"),
    "PRICE_HISTORY_SPY": lambda: YahooHistoryConnector("SPY", period="6mo", interval="1d"),
    "SEC_AAPL_EPS": lambda: SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent=SEC_USER_AGENT),
    "CRYPTO_BTC": lambda: BinanceFuturesConnector("BTCUSDT", history_limit=30),
    "MARKET_NEWS": lambda: NewsRssConnector(NEWS_RSS_URL),
}

for key, factory in REGISTRATIONS.items():
    if not manager.is_registered(key):
        manager.register(key, primary=factory())

if st.button("🔄 Refresh all data sources now", type="primary"):
    with st.spinner("Fetching from every registered source..."):
        for key in REGISTRATIONS:
            manager.get(key, force_refresh=True)
    st.success("Refresh complete.")

status = manager.status_report()

if not status:
    st.info("No datasets fetched yet this session — click **Refresh all data sources now** above.")
else:
    rows = []
    for entry in status:
        rows.append({
            "Dataset": entry["name"],
            "Source": entry["source"],
            "Status": entry["validation_status"],
            "Quality": entry["quality_score"],
            "Age (s)": entry["age_seconds"],
            "Usable now": "✅" if entry["usable_now"] else "❌",
        })
    df = pd.DataFrame(rows).sort_values("Dataset")
    st.dataframe(df, width="stretch", hide_index=True)

    unusable = [r for r in rows if r["Usable now"] == "❌"]
    if unusable:
        st.warning(
            f"{len(unusable)} of {len(rows)} datasets are not currently usable — this is the correct, "
            f"honest state when a source is unreachable or stale, not an error to suppress. Departments "
            f"reading these will report reduced confidence and list them as data gaps."
        )

st.divider()
st.caption(
    "This page shares its DataIntegrityManager instance with every other dashboard page in this "
    "session — a dataset refreshed here is served from cache (within its TTL) elsewhere too."
)
