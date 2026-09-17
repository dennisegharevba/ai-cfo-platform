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

"risk_fundamentals" (real per-asset volatility/drawdown, see
agents/chief_risk_fundamentals_officer.py) is wired in across ALL asset
classes covered by this watchlist — commodities, currency (FX), equities,
and crypto — per an explicit later request to extend risk coverage
beyond commodities. Equities in particular carry a real, known cost from
this: ~350 additional Yahoo Finance requests added to the weekly cycle,
accepted explicitly rather than added silently (this watchlist originally
deferred that exact addition for exactly that reason).

Both lists are built programmatically from config/cftc_markets.py and
config/sp500_tickers.py rather than typed out by hand — see those files'
docstrings for important caveats about list accuracy (best-effort/
point-in-time, not verified against a live source from this environment).
The FX and crypto Yahoo ticker mappings below (FX_YAHOO_TICKERS,
CRYPTO_YAHOO_TICKERS) carry the same caveat.
"""

from config.cftc_markets import FX_FUTURES_MARKETS, COMMODITY_FUTURES_MARKETS
from config.sp500_tickers import LARGE_CAP_TICKERS

# Yahoo Finance futures tickers for commodities that have one — used by the
# "risk_fundamentals" department (volatility/drawdown from price history).
# Commodities not listed here simply don't get a risk_fundamentals entry
# (no fabricated ticker guess) rather than being silently skipped from the
# loop below in a way that would be hard to notice.
COMMODITY_YAHOO_TICKERS = {
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Copper": "HG=F",
    "Platinum": "PL=F",
    "Palladium": "PA=F",
    "WTI Crude Oil": "CL=F",
    "Natural Gas": "NG=F",
    "Corn": "ZC=F",
    "Wheat": "ZW=F",
    "Soybeans": "ZS=F",
}

# Yahoo Finance FX tickers, following Yahoo's own (slightly quirky)
# convention: pairs quoted as XXX/USD use "XXXUSD=X"; pairs quoted as
# USD/XXX use just "XXX=X" (not "USDXXX=X"). Same best-effort caveat as
# COMMODITY_YAHOO_TICKERS and every other "verify against a live source"
# file in this project (config/cftc_markets.py, config/sp500_tickers.py,
# config/fomc_meeting_dates.py) — not verified against a live Yahoo
# Finance response from this environment (no network access here). Run
# scripts/verify_watchlist_markets.py once you have network access to
# confirm every one of these actually resolves.
FX_YAHOO_TICKERS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CHF": "CHF=X",
    "USD/CAD": "CAD=X",
    "USD/MXN": "MXN=X",
    "USD/BRL": "BRL=X",
    "USD/ZAR": "ZAR=X",
    # DXY (the Dollar Index itself, not a currency pair) uses a different
    # Yahoo ticker convention entirely — "DX-Y.NYB" is the commonly-cited
    # one, but this is the least-confident entry in this mapping; verify
    # it specifically before relying on it.
    "DXY": "DX-Y.NYB",
}

# Yahoo Finance crypto tickers — the "BTC-USD" style suffix is Yahoo's
# well-established, widely-documented convention (more consistently
# reliable than the FX tickers above, but still worth a quick check via
# verify_watchlist_markets.py if you're extending this list).
CRYPTO_YAHOO_TICKERS = {
    "BTC": "BTC-USD",
}

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
            "risk_fundamentals": {"ticker": CRYPTO_YAHOO_TICKERS["BTC"]},
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
# currency), so FX entries use "fx" as the primary department, matching
# the original Phase 3 design — plus "risk_fundamentals" (real volatility/
# drawdown from Yahoo Finance FX price history) where a Yahoo ticker is
# known, per an explicit later request to extend risk coverage beyond
# commodities to currency, equities, and crypto too.
for _display_name, _market_name in FX_FUTURES_MARKETS.items():
    _fx_departments = {"fx": {"cot_market": _market_name}}
    _fx_yahoo_ticker = FX_YAHOO_TICKERS.get(_display_name)
    if _fx_yahoo_ticker is not None:
        _fx_departments["risk_fundamentals"] = {"ticker": _fx_yahoo_ticker}
    WATCHLIST_DAILY.append({
        "asset_or_theme": _display_name,
        "departments": _fx_departments,
    })

# One entry per commodity future. Every commodity gets "commodity"
# (COT/speculative positioning), "commodity_fundamentals", "seasonality",
# and — where a Yahoo Finance futures ticker is known — "risk_fundamentals",
# for a uniform department shape across the whole watchlist. Some of these
# departments currently only have real configured data for a subset of
# commodities (see agents/chief_commodity_fundamentals_officer.py's
# COMMODITY_FACTOR_SPECS and agents/seasonality_scoring.py's
# SEASONALITY_PATTERNS) — every other commodity's department runs and
# honestly reports neutral/zero-confidence/HIGH risk (score_category()'s
# correct behavior for an empty factor list) rather than being silently
# omitted, matching the same transparency reasoning already established
# for commodity_fundamentals: a uniform department count is more legible
# for a hedge-fund-terminal-style dashboard than one that varies silently
# per commodity, and it's still never a fabricated reading.
for _display_name, _market_name in COMMODITY_FUTURES_MARKETS.items():
    _departments = {
        "commodity": {"cot_market": _market_name},
        "commodity_fundamentals": {},
        "seasonality": {},
    }
    _yahoo_ticker = COMMODITY_YAHOO_TICKERS.get(_display_name)
    if _yahoo_ticker is not None:
        _departments["risk_fundamentals"] = {"ticker": _yahoo_ticker}
    WATCHLIST_DAILY.append({
        "asset_or_theme": _display_name,
        "departments": _departments,
    })

# Two equity-index entries specifically to exercise the S&P500/NASDAQ100
# seasonality patterns configured in agents/seasonality_scoring.py — using
# the SPY/QQQ ETFs as Yahoo Finance proxies (far more reliably fetchable
# via yfinance than the raw index symbols).
WATCHLIST_DAILY.append({
    "asset_or_theme": "S&P500",
    "departments": {"seasonality": {}, "risk_fundamentals": {"ticker": "SPY"}},
})
WATCHLIST_DAILY.append({
    "asset_or_theme": "NASDAQ100",
    "departments": {"seasonality": {}, "risk_fundamentals": {"ticker": "QQQ"}},
})

# The weekly equity sweep: one entry per ticker. No "cik" param needed —
# run_daily_cycle.py's equity runner resolves it automatically via
# connectors.sec_ticker_lookup.resolve_cik(). "risk_fundamentals" uses the
# ticker itself directly (no mapping needed — equity tickers are already
# Yahoo-compatible as-is).
#
# UPDATE: this originally deliberately did NOT include risk_fundamentals,
# documented as "would triple this cycle's weekly request volume (~350
# more Yahoo Finance calls) without an explicit request to take on that
# cost." That request was later made explicitly — risk_fundamentals is
# now included for every equity too. The added weekly request volume is a
# real, known tradeoff (worth knowing if you ever see this cycle running
# noticeably longer or hitting Yahoo Finance rate limits), made with that
# tradeoff stated plainly rather than added silently.
WATCHLIST_WEEKLY = [
    {
        "asset_or_theme": ticker,
        "departments": {
            "equity": {},
            "risk_fundamentals": {"ticker": ticker},
        },
    }
    for ticker in LARGE_CAP_TICKERS
]

# Kept for backward compatibility with anything importing the original
# name — the daily list is the closest equivalent to what WATCHLIST used
# to mean before it was split.
WATCHLIST = WATCHLIST_DAILY
