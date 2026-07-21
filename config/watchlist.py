"""
What the automated research cycle (scripts/run_daily_cycle.py) covers.

Split into two watchlists, run on two different schedules
(.github/workflows/scheduled_run.yml and scheduled_run_equities.yml):

    WATCHLIST_DAILY   — macro, all major FX futures, all major commodity
                         futures, crypto, sentiment. These change daily/
                         weekly and are cheap to refresh (COT is one call
                         per market, no SEC EDGAR involved).

    WATCHLIST_WEEKLY  — the broad equity universe (config/sp500_tickers.py).
                         Deliberately run WEEKLY, not daily: EPS/revenue
                         come from quarterly filings, so re-fetching them
                         every weekday provides zero additional signal —
                         it would only be unnecessary load on SEC EDGAR
                         (~350 tickers x 2 EDGAR calls = ~700 requests) for
                         data that hasn't changed since the last run.

Both lists are built programmatically from config/cftc_markets.py and
config/sp500_tickers.py rather than typed out by hand — see those files'
docstrings for important caveats about list accuracy (best-effort/
point-in-time, not verified against a live source from this environment).
"""

from config.cftc_markets import FX_FUTURES_MARKETS, COMMODITY_FUTURES_MARKETS
from config.sp500_tickers import LARGE_CAP_TICKERS

WATCHLIST_DAILY = [
    {
        "asset_or_theme": "US Macro Outlook",
        "departments": {
            "macro": {},
            "bond": {},
        },
    },
    {
        "asset_or_theme": "BTC",
        "departments": {
            "crypto": {"symbol": "BTCUSDT"},
        },
    },
    {
        "asset_or_theme": "Broad Market Sentiment",
        "departments": {
            "sentiment": {},
        },
    },
]

# One entry per FX future: COT positioning + a technical read isn't
# available for most of these (no simple equivalent ETF/ticker for every
# currency), so FX entries use "fx" only, matching the original Phase 3 design.
for _display_name, _market_name in FX_FUTURES_MARKETS.items():
    WATCHLIST_DAILY.append({
        "asset_or_theme": _display_name,
        "departments": {
            "fx": {"cot_market": _market_name},
        },
    })

# One entry per commodity future.
for _display_name, _market_name in COMMODITY_FUTURES_MARKETS.items():
    WATCHLIST_DAILY.append({
        "asset_or_theme": _display_name,
        "departments": {
            "commodity": {"cot_market": _market_name},
        },
    })

# The weekly equity sweep: one entry per ticker. No "cik" param needed —
# run_daily_cycle.py's equity runner resolves it automatically via
# connectors.sec_ticker_lookup.resolve_cik().
WATCHLIST_WEEKLY = [
    {
        "asset_or_theme": ticker,
        "departments": {
            "equity": {},
            "technical": {"ticker": ticker},
        },
    }
    for ticker in LARGE_CAP_TICKERS
]

# Kept for backward compatibility with anything importing the original
# name — the daily list is the closest equivalent to what WATCHLIST used
# to mean before it was split.
WATCHLIST = WATCHLIST_DAILY
