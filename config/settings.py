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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# SEC EDGAR requires a descriptive User-Agent with real contact info —
# see connectors/sec_edgar_connector.py
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")

# Minimum quality score (0-100) a dataset must have to be considered usable
# by any agent. Configurable per the spec's "block on unavailable/low quality" rule.
MIN_DATA_QUALITY = float(os.getenv("MIN_DATA_QUALITY", "60"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
