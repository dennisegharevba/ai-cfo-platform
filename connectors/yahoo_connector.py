"""
Yahoo Finance connector (via the `yfinance` package).

Free, no API key required. Used as the default price source for equities,
indices, ETFs, and futures continuous contracts. Also registered as the
backup source for crypto (primary would be an exchange API like Binance).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from core.data_source import DataSource, DataSourceError


class YahooConnector(DataSource):
    name = "YAHOO"
    default_ttl_seconds = 45  # per spec: stock/futures prices every 30-60s

    def __init__(self, ticker: str):
        self.ticker = ticker

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise DataSourceError(
                "yfinance is not installed. Run: pip install yfinance"
            ) from exc

        try:
            tkr = yf.Ticker(self.ticker)
            info = tkr.fast_info
            last_price = info.get("last_price") if hasattr(info, "get") else getattr(info, "last_price", None)
            if last_price is None:
                # fast_info can behave like an object rather than a dict depending on version
                last_price = info["lastPrice"] if "lastPrice" in info else None
        except Exception as exc:  # yfinance raises varied exception types
            raise DataSourceError(f"Yahoo Finance request failed for {self.ticker}: {exc}") from exc

        if last_price is None:
            raise DataSourceError(f"Yahoo Finance returned no price for {self.ticker}")

        payload = {
            "ticker": self.ticker,
            "last_price": float(last_price),
        }
        # Yahoo's fast_info doesn't expose a clean "as of" timestamp reliably;
        # treat fetch time as the provider timestamp for this connector.
        provider_ts = datetime.now(timezone.utc)
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        price = payload.get("last_price")
        return isinstance(price, (int, float)) and price > 0
