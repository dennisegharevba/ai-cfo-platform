"""
Default refresh intervals (TTL, in seconds) by data category.

These are defaults per the platform spec — override per-registration in
core.DataIntegrityManager.register(..., ttl_seconds=...) if a specific
dataset needs something different.
"""

REFRESH_INTERVALS_SECONDS = {
    "stock_price": 45,          # 30-60s
    "futures_price": 45,        # 30-60s
    "crypto_price": 10,         # 5-15s
    "news": 60,                 # every minute
    "economic_calendar": 300,   # every 5 minutes
    "treasury_yields": 60,      # every minute
    "cot_report": 60 * 60 * 24 * 7,   # weekly, force-refresh on publish day instead
    "usda_report": 60 * 60 * 24,      # daily poll, event-driven refresh on release
    "eia_report": 60 * 60,            # hourly poll, event-driven refresh on release
    "earnings": 60 * 60,              # hourly poll, event-driven refresh on release
    "insider_transactions": 60 * 60 * 24,  # daily
}
