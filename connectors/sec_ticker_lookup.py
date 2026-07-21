"""
SEC ticker -> CIK lookup connector.

SEC publishes a single free JSON file mapping every registered ticker to
its CIK: https://www.sec.gov/files/company_tickers.json — no API key,
just the same descriptive User-Agent every other SEC EDGAR call needs.

This is the connector that makes broad equity coverage practical: instead
of hand-typing a CIK for every ticker you want to cover (error-prone, and
the reason Phase 4/11's original demo only covered Apple), one fetch of
this file resolves ALL tickers at once. The Chief Equity Analyst still
needs its own per-ticker calls for actual fundamentals (EPS/revenue) — this
connector only removes the CIK-lookup step.

Long TTL (24h) since this mapping changes rarely (new SEC registrants,
ticker changes) — refetching it every cycle would be pure waste.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from core.data_source import DataSource, DataSourceError

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"


class SecTickerCikConnector(DataSource):
    name = "SEC_TICKER_CIK_MAP"
    default_ttl_seconds = 60 * 60 * 24  # 24h — this mapping changes rarely

    def __init__(self, user_agent: str, timeout: int = 20):
        self.user_agent = user_agent
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        if not self.user_agent:
            raise DataSourceError("SEC_USER_AGENT is not set — SEC requires a descriptive User-Agent header")

        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        try:
            resp = requests.get(TICKER_MAP_URL, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"SEC ticker/CIK map request failed: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"SEC ticker/CIK map returned invalid JSON: {exc}") from exc

        # The file's shape is {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, "1": {...}, ...}
        ticker_to_cik = {}
        for entry in data.values():
            ticker = entry.get("ticker")
            cik = entry.get("cik_str")
            if ticker and cik is not None:
                ticker_to_cik[ticker.upper()] = str(cik).zfill(10)

        if not ticker_to_cik:
            raise DataSourceError("SEC ticker/CIK map returned no usable entries")

        payload = {"ticker_to_cik": ticker_to_cik, "count": len(ticker_to_cik)}
        return payload, datetime.now(timezone.utc)

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        mapping = payload.get("ticker_to_cik")
        # Sanity-check a couple of tickers that should always be present.
        return isinstance(mapping, dict) and "AAPL" in mapping and "MSFT" in mapping


def resolve_cik(manager, ticker: str, user_agent: str, key: str = "SEC_TICKER_CIK_MAP") -> Optional[str]:
    """
    Convenience helper: registers the ticker/CIK map connector if needed,
    fetches (or reuses the cached) mapping through the DataIntegrityManager,
    and returns the CIK for `ticker` — or None if the map isn't usable right
    now or doesn't contain that ticker.

    Callers (run_daily_cycle.py, the dashboard) should treat None the same
    way any other missing dataset is treated: skip/degrade gracefully,
    never fabricate a CIK.
    """
    if not manager.is_registered(key):
        manager.register(key, primary=SecTickerCikConnector(user_agent=user_agent))

    dataset = manager.get(key)
    if not dataset.is_usable():
        return None

    return dataset.payload.get("ticker_to_cik", {}).get(ticker.upper())
