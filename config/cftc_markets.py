"""
Major CFTC Commitment of Traders market names for currency and commodity
futures — used to build the FX/commodity portion of config/watchlist.py.

IMPORTANT — the same caveat as config/sp500_tickers.py applies here, even
more so: CFTC's exact `market_and_exchange_names` strings must match
EXACTLY (including punctuation) for connectors.cot_connector.CotConnector
to find any data. These are assembled from general knowledge of the
Legacy Futures-Only report, not verified against a live query — some may
be slightly off (a naming variant, a discontinued contract, etc.).

This is safe to ship anyway because of how the platform is built: a wrong
market name doesn't crash anything — CotConnector raises DataSourceError
("No COT rows returned"), which run_daily_cycle.py already isolates
per-asset (see docs/ARCHITECTURE_PHASE11.md), so a bad entry here just
shows up as one blocked/degraded asset in the cycle summary, not a broken
run. Still — run scripts/verify_watchlist_markets.py once you have network
access to find out exactly which entries (if any) need fixing, rather than
discovering it piecemeal from degraded reports.

To find/confirm the exact correct string for a market CFTC tracks:
https://publicreporting.cftc.gov/resource/6dca-aqww.json accepts a
`market_and_exchange_names` filter — searching CFTC's own COT report
finder (https://www.cftc.gov/MarketReports/CommitmentsofTraders) for a
given commodity/currency will show its exact reporting name.
"""

# Friendly display name -> CFTC market_and_exchange_names string
FX_FUTURES_MARKETS = {
    "EUR/USD": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "USD/JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "GBP/USD": "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE",
    "USD/CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "USD/CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "AUD/USD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "NZD/USD": "NEW ZEALAND DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "USD/MXN": "MEXICAN PESO - CHICAGO MERCANTILE EXCHANGE",
    "USD/BRL": "BRAZILIAN REAL - CHICAGO MERCANTILE EXCHANGE",
    "USD/ZAR": "SOUTH AFRICAN RAND - CHICAGO MERCANTILE EXCHANGE",
    "DXY": "USD INDEX - ICE FUTURES U.S.",
}

COMMODITY_FUTURES_MARKETS = {
    "Gold": "GOLD - COMMODITY EXCHANGE INC.",
    "Silver": "SILVER - COMMODITY EXCHANGE INC.",
    "Copper": "COPPER-GRADE #1 - COMMODITY EXCHANGE INC.",
    "Platinum": "PLATINUM - NEW YORK MERCANTILE EXCHANGE",
    "Palladium": "PALLADIUM - NEW YORK MERCANTILE EXCHANGE",
    "WTI Crude Oil": "WTI FINANCIAL CRUDE OIL - NEW YORK MERCANTILE EXCHANGE",
    "Natural Gas": "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE",
    "Corn": "CORN - CHICAGO BOARD OF TRADE",
    "Wheat": "WHEAT-SRW - CHICAGO BOARD OF TRADE",
    "Soybeans": "SOYBEANS - CHICAGO BOARD OF TRADE",
    "Soybean Oil": "SOYBEAN OIL - CHICAGO BOARD OF TRADE",
    "Soybean Meal": "SOYBEAN MEAL - CHICAGO BOARD OF TRADE",
    "Cotton": "COTTON NO. 2 - ICE FUTURES U.S.",
    "Coffee": "COFFEE C - ICE FUTURES U.S.",
    "Cocoa": "COCOA - ICE FUTURES U.S.",
    "Sugar": "SUGAR NO. 11 - ICE FUTURES U.S.",
    "Live Cattle": "LIVE CATTLE - CHICAGO MERCANTILE EXCHANGE",
    "Lean Hogs": "LEAN HOGS - CHICAGO MERCANTILE EXCHANGE",
    "Feeder Cattle": "FEEDER CATTLE - CHICAGO MERCANTILE EXCHANGE",
}
