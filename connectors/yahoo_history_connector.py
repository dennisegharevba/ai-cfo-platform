"""
Yahoo Finance historical price connector (via `yfinance`), separate from
Phase 1's YahooConnector (which fetches only the latest single price at a
45s TTL — fine for a live quote, useless for indicator math). This connector
fetches a window of daily closes for RSI/MACD/trend calculations, at a
much longer TTL since technical indicators built on daily bars don't need
per-minute refreshing.

Free, no API key required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from core.data_source import DataSource, DataSourceError


class YahooHistoryConnector(DataSource):
    name = "YAHOO_HISTORY"
    default_ttl_seconds = 60 * 60  # daily-bar indicators don't need frequent refresh

    def __init__(self, ticker: str, period: str = "6mo", interval: str = "1d"):
        """
        ticker: Yahoo Finance ticker, e.g. "AAPL", "SPY", "GC=F" (gold futures).
        period/interval: passed straight to yfinance's Ticker.history();
            defaults give ~6 months of daily closes, comfortably enough for
            RSI(14), MACD(12,26,9), and a 20/50 SMA trend read.
        """
        self.ticker = ticker
        self.period = period
        self.interval = interval

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise DataSourceError("yfinance is not installed. Run: pip install yfinance") from exc

        try:
            df = yf.Ticker(self.ticker).history(period=self.period, interval=self.interval)
        except Exception as exc:  # yfinance raises varied exception types
            raise DataSourceError(f"Yahoo Finance history request failed for {self.ticker}: {exc}") from exc

        if df is None or df.empty or "Close" not in df.columns:
            raise DataSourceError(f"Yahoo Finance returned no history for {self.ticker}")

        # yfinance returns rows oldest-first with a DatetimeIndex; convert to
        # this platform's newest-first convention.
        history = [
            {"date": idx.isoformat(), "close": float(row["Close"])}
            for idx, row in df.iterrows()
        ]
        history.reverse()

        payload = {
            "ticker": self.ticker,
            "latest_close": history[0]["close"],
            "latest_date": history[0]["date"],
            "history": history,
        }
        provider_ts = datetime.now(timezone.utc)
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("latest_close") is None:
            return False
        history = payload.get("history")
        # Require enough bars for the longest indicator window (MACD needs
        # slow(26)+signal(9)=35) to even be attemptable; agents themselves
        # still check indicator-specific minimums and degrade gracefully.
        return isinstance(history, list) and len(history) >= 20
