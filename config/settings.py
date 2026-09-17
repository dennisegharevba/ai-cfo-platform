"""
Central configuration, loaded from environment variables (.env in local dev).

Never hardcode secrets. Copy .env.example to .env and fill in your own keys.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional in production if env vars are set another way

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# SEC EDGAR requires a descriptive User-Agent with real contact info —
# see connectors/sec_edgar_connector.py
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")

# Public market-news RSS feed used by the Chief Sentiment Officer.
# Default: MarketWatch's public top-stories feed (free, no key).
# UPDATED per a live finding: the "topstories" feed was confirmed
# (twice, independently) to return 0 of 10 genuinely market-relevant
# headlines — entirely MarketWatch personal-finance advice-column
# content ("should I pay off my mortgage?", "how do I care for my
# elderly relative?"), not market/economic news. MarketPulse, tested
# side by side via scripts/debug_news_feeds.py, returned real, current,
# market-moving headlines (jobless claims, consumer credit data, a
# market-moving geopolitical headline) and genuinely triggered a
# sentiment keyword match. See docs/ARCHITECTURE_NEWS_FEED_FIX.md.
NEWS_RSS_URL = os.getenv("NEWS_RSS_URL") or "http://feeds.marketwatch.com/marketwatch/marketpulse/"

# Minimum quality score (0-100) a dataset must have to be considered usable
# by any agent. Configurable per the spec's "block on unavailable/low quality" rule.
MIN_DATA_QUALITY = float(os.getenv("MIN_DATA_QUALITY", "60"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Whether Commercial (producer/hedger) COT positioning is shown anywhere in
# the platform (dashboard, reports, alerts, investment committee summaries)
# as INFORMATIONAL/supplementary context. Defaults to disabled — per an
# explicit later decision, Commercial positioning was removed as a
# directional input to the Chief Commodity/FX Analyst entirely, and this
# flag does NOT bring it back into scoring even when enabled; it only
# controls whether an informational line is displayed. See
# docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md.
ENABLE_COMMERCIAL_POSITIONING_DISPLAY = os.getenv("ENABLE_COMMERCIAL_POSITIONING_DISPLAY", "false").lower() in ("1", "true", "yes")

# Whether the Swing Signal feature's Telegram alerts (the automatic path in
# scripts/run_daily_cycle.py AND the dashboard's manual "Send Telegram alert"
# button on 8_Swing_Signals.py) are allowed to actually fire. Defaults to
# DISABLED: a real backtest across three independent, largely uncorrelated
# assets (Gold, EUR/USD, WTI Crude Oil — see docs/ARCHITECTURE_SWING_SIGNAL.md's
# "Backtesting" section, updated 2026-09-11) found a consistent NEGATIVE
# correlation with forward returns and a losing simulated strategy (profit
# factor under 1.0) on all three. Signals still DETECT and PERSIST normally
# either way — the dashboard and database keep accumulating real data — only
# the Telegram SEND is gated, so nothing here silently trusts an alert path
# that hasn't earned it yet. Flip to true only once the fade hypothesis, a
# reworked confidence model, or further evidence resolves this.
SWING_SIGNAL_ALERTS_ENABLED = os.getenv("SWING_SIGNAL_ALERTS_ENABLED", "false").lower() in ("1", "true", "yes")

# Alpaca broker credentials (execution layer — see docs/ARCHITECTURE_EXECUTION_LAYER.md).
# Deliberately NO live-trading flag here. brokers.alpaca_connector.AlpacaConnector
# always defaults to paper trading regardless of anything in this file or .env —
# enabling live trading requires live_trading_confirmed=True passed explicitly in
# code, every time, precisely so a forgotten config value can never silently arm it.
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
