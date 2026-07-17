"""
Binance USD-M Futures connector — open interest history + funding rate.

Free, public endpoints, no API key required:
    GET /futures/data/openInterestHist  -> historical open interest
    GET /fapi/v1/premiumIndex           -> current mark price + funding rate

Used by the Chief Cryptocurrency Analyst. Funding rate sign/magnitude is
treated as the primary sentiment signal (positive = longs paying shorts a
premium = bullish positioning dominance); open interest trend is a secondary
confirmation of how much conviction is behind that positioning. See
agents/crypto_scoring.py for the scoring logic itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from core.data_source import DataSource, DataSourceError

OPEN_INTEREST_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"


class BinanceFuturesConnector(DataSource):
    name = "BINANCE_FUTURES"
    default_ttl_seconds = 30  # per spec: crypto every 5-15s for price; 30s is reasonable for OI/funding

    def __init__(self, symbol: str, history_limit: int = 30, timeout: int = 10):
        """
        symbol: Binance USD-M futures symbol, e.g. "BTCUSDT", "ETHUSDT".
        history_limit: how many recent open-interest-history data points
            (default period "1d" -> ~history_limit days) to fetch for trend scoring.
        """
        self.symbol = symbol.upper()
        self.history_limit = max(history_limit, 2)
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        oi_params = {"symbol": self.symbol, "period": "1d", "limit": self.history_limit}
        try:
            oi_resp = requests.get(OPEN_INTEREST_HIST_URL, params=oi_params, timeout=self.timeout)
            oi_resp.raise_for_status()
            oi_rows = oi_resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"Binance open interest history request failed for {self.symbol}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"Binance open interest history returned invalid JSON: {exc}") from exc

        if not oi_rows:
            raise DataSourceError(f"No open interest history returned for {self.symbol}")

        try:
            funding_resp = requests.get(PREMIUM_INDEX_URL, params={"symbol": self.symbol}, timeout=self.timeout)
            funding_resp.raise_for_status()
            funding_data = funding_resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"Binance premium index request failed for {self.symbol}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"Binance premium index returned invalid JSON: {exc}") from exc

        # Binance returns openInterestHist oldest-first; normalize to newest-first
        # to match this platform's convention (FRED, CFTC COT connectors).
        history = [
            {"date": row.get("timestamp"), "open_interest": row.get("sumOpenInterest")}
            for row in oi_rows
        ]
        history.reverse()

        try:
            funding_rate = float(funding_data.get("lastFundingRate"))
        except (TypeError, ValueError):
            raise DataSourceError(f"Binance premium index returned no usable funding rate for {self.symbol}")

        provider_ts = None
        time_ms = funding_data.get("time")
        if time_ms:
            try:
                provider_ts = datetime.fromtimestamp(int(time_ms) / 1000, tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                pass

        payload = {
            "symbol": self.symbol,
            "latest_open_interest": history[0].get("open_interest"),
            "latest_funding_rate": funding_rate,
            "history": history,
        }
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("latest_funding_rate") is None:
            return False
        return isinstance(payload.get("history"), list) and len(payload["history"]) > 0
