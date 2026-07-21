"""
Verification tool for config/cftc_markets.py and config/sp500_tickers.py.

Both of those files carry an honest caveat: their CFTC market names and
ticker list were assembled from general knowledge, not verified against a
live source. This script checks every one of them against the real APIs
and reports which (if any) don't actually resolve — run it once, with
network access, before relying heavily on the automated cycle.

Run:
    python scripts/verify_watchlist_markets.py

This makes real network calls (CFTC's public COT API and SEC's ticker/CIK
map) — it needs internet access and, for the ticker check, SEC_USER_AGENT
set in your environment/.env.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import SEC_USER_AGENT
from config.cftc_markets import FX_FUTURES_MARKETS, COMMODITY_FUTURES_MARKETS
from config.sp500_tickers import LARGE_CAP_TICKERS
from connectors.cot_connector import CotConnector
from connectors.sec_ticker_lookup import SecTickerCikConnector
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


if __name__ == "__main__":
    check_cftc_markets()
    check_tickers()
