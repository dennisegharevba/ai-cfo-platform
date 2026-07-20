"""
WATCHLIST: what the scheduled daily research cycle (scripts/run_daily_cycle.py)
actually runs. Each entry names an asset/theme and which departments to run
against it, with whatever per-department parameters that department needs
(a CFTC market name, a ticker, a Binance symbol, etc.).

Edit this list to change what the automated cycle covers — no code changes
needed in the runner itself.
"""

WATCHLIST = [
    {
        "asset_or_theme": "US Macro Outlook",
        "departments": {
            "macro": {},
            "bond": {},
        },
    },
    {
        "asset_or_theme": "Gold",
        "departments": {
            "commodity": {"cot_market": "GOLD - COMMODITY EXCHANGE INC."},
            "technical": {"ticker": "GLD"},
            "sentiment": {},
        },
    },
    {
        "asset_or_theme": "EUR/USD",
        "departments": {
            "fx": {"cot_market": "EURO FX - CHICAGO MERCANTILE EXCHANGE"},
            "technical": {"ticker": "FXE"},
        },
    },
    {
        "asset_or_theme": "AAPL",
        "departments": {
            "equity": {"cik": "320193"},
            "technical": {"ticker": "AAPL"},
        },
    },
    {
        "asset_or_theme": "BTC",
        "departments": {
            "crypto": {"symbol": "BTCUSDT"},
        },
    },
]
