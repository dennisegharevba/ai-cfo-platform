"""
Verification tool for every "best-effort, not verified live" data mapping
in this platform: config/cftc_markets.py's CFTC market names,
config/sp500_tickers.py's equity ticker list, config/watchlist.py's
FX/commodity/crypto Yahoo Finance ticker mappings, and
agents/chief_commodity_fundamentals_officer.py's EIA API routes.

Every one of these was assembled from general knowledge, not verified
against a live source, since this development environment has no network
access. This script checks every one of them against the real APIs and
reports which (if any) don't actually resolve — run it once, with network
access, before relying heavily on the automated cycle.

Run:
    python scripts/verify_watchlist_markets.py

This makes real network calls (CFTC's public COT API, SEC's ticker/CIK
map, Yahoo Finance, and the EIA API) — it needs internet access, and for
the equity-ticker and EIA checks specifically, SEC_USER_AGENT and
EIA_API_KEY set in your environment/.env respectively (both checks are
skipped gracefully, not crashed on, if their key isn't set).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import SEC_USER_AGENT, EIA_API_KEY
from config.cftc_markets import FX_FUTURES_MARKETS, COMMODITY_FUTURES_MARKETS
from config.sp500_tickers import LARGE_CAP_TICKERS
from config.watchlist import FX_YAHOO_TICKERS, COMMODITY_YAHOO_TICKERS, CRYPTO_YAHOO_TICKERS
from connectors.cot_connector import CotConnector
from connectors.sec_ticker_lookup import SecTickerCikConnector
from connectors.yahoo_history_connector import YahooHistoryConnector
from connectors.eia_connector import EiaConnector
from agents.chief_commodity_fundamentals_officer import EIA_ROUTE_SPECS
from core.data_source import DataSourceError


def check_cftc_markets():
    print("\n=== Checking CFTC market names (FX + commodities) ===")
    all_markets = {**FX_FUTURES_MARKETS, **COMMODITY_FUTURES_MARKETS}
    bad = []
    for display_name, market_name in all_markets.items():
        try:
            CotConnector(market_name, weeks_history=2).fetch()
            print(f"  OK    {display_name}: \"{market_name}\"")
        except DataSourceError as exc:
            bad.append((display_name, market_name))
            print(f"  BAD   {display_name}: \"{market_name}\" — {exc}")

    if bad:
        print(f"\n{len(bad)} market name(s) need fixing in config/cftc_markets.py:")
        for display_name, market_name in bad:
            print(f"  - {display_name}")
        print(
            "\nTo find the correct exact string: search CFTC's COT report finder "
            "(https://www.cftc.gov/MarketReports/CommitmentsofTraders) for the "
            "commodity/currency, or query "
            "https://publicreporting.cftc.gov/resource/6dca-aqww.json directly."
        )
    else:
        print("\nAll CFTC market names resolved correctly.")


def check_tickers():
    print("\n=== Checking equity tickers against SEC's ticker/CIK map ===")
    if not SEC_USER_AGENT:
        print("  SEC_USER_AGENT is not set — skipping. Set it in .env and re-run.")
        return

    try:
        payload, _ = SecTickerCikConnector(user_agent=SEC_USER_AGENT).fetch()
    except DataSourceError as exc:
        print(f"  Could not fetch SEC's ticker/CIK map: {exc}")
        return

    ticker_to_cik = payload["ticker_to_cik"]
    missing = [t for t in LARGE_CAP_TICKERS if t.upper() not in ticker_to_cik]

    print(f"  {len(LARGE_CAP_TICKERS) - len(missing)} of {len(LARGE_CAP_TICKERS)} tickers found.")
    if missing:
        print(f"\n{len(missing)} ticker(s) not found in SEC's map (may be delisted, merged, or a typo):")
        for t in missing:
            print(f"  - {t}")
        print(
            "\nThese will simply degrade to zero-confidence reports in the automated "
            "cycle (see docs/ARCHITECTURE_PHASE11.md) rather than break anything — "
            "but worth removing or fixing in config/sp500_tickers.py if you notice "
            "a lot of them."
        )
    else:
        print("All tickers resolved correctly.")


def check_yahoo_tickers():
    print("\n=== Checking Yahoo Finance tickers (FX + commodities + crypto) ===")
    print("(Equity tickers are checked separately below via SEC's ticker/CIK map, "
          "and equity tickers ARE the Yahoo ticker directly, so no separate check needed there.)")
    all_tickers = {**FX_YAHOO_TICKERS, **COMMODITY_YAHOO_TICKERS, **CRYPTO_YAHOO_TICKERS}
    bad = []
    for display_name, ticker in all_tickers.items():
        try:
            YahooHistoryConnector(ticker, period="1mo", interval="1d").fetch()
            print(f"  OK    {display_name}: \"{ticker}\"")
        except DataSourceError as exc:
            bad.append((display_name, ticker))
            print(f"  BAD   {display_name}: \"{ticker}\" — {exc}")

    if bad:
        print(f"\n{len(bad)} Yahoo ticker(s) need fixing in config/watchlist.py:")
        for display_name, ticker in bad:
            print(f"  - {display_name} (\"{ticker}\")")
        print(
            "\nThese were flagged as best-effort/not-verified when originally added — see "
            "config/watchlist.py's own docstring for each mapping (FX_YAHOO_TICKERS especially, "
            "since Yahoo's FX ticker convention is genuinely inconsistent between pairs). "
            "Double-check the exact symbol at https://finance.yahoo.com."
        )
    else:
        print("\nAll Yahoo Finance tickers resolved correctly.")


def check_eia_routes():
    print("\n=== Checking EIA API routes (energy commodity fundamentals) ===")
    if not EIA_API_KEY:
        print("  EIA_API_KEY is not set — skipping. Get a free key at "
              "https://www.eia.gov/opendata/register.php and set it in .env, then re-run.")
        return

    bad = []
    for (commodity, suffix), (route, facets) in EIA_ROUTE_SPECS.items():
        try:
            EiaConnector(route=route, facets=facets, api_key=EIA_API_KEY, periods_history=2).fetch()
            print(f"  OK    {commodity} / {suffix}: route=\"{route}\"")
        except DataSourceError as exc:
            bad.append((commodity, suffix, route))
            print(f"  BAD   {commodity} / {suffix}: route=\"{route}\" — {exc}")

    if bad:
        print(f"\n{len(bad)} EIA route(s) need fixing in agents/chief_commodity_fundamentals_officer.py:")
        for commodity, suffix, route in bad:
            print(f"  - {commodity} / {suffix} (\"{route}\")")
        print(
            "\nThese were flagged as best-effort/not-verified when originally added — see "
            "connectors/eia_connector.py's own docstring. Double-check the exact route/facets "
            "at EIA's own API browser: https://www.eia.gov/opendata/browser/"
        )
    else:
        print("\nAll EIA routes resolved correctly.")


if __name__ == "__main__":
    check_cftc_markets()
    check_tickers()
    check_yahoo_tickers()
    check_eia_routes()
