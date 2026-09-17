"""
FRED (Federal Reserve Economic Data) connector.

Free API. Requires a free API key from https://fred.stlouisfed.org/docs/api/api_key.html
Set FRED_API_KEY in your environment (see config/settings.py and .env.example).

Used by the Chief Macro Officer / Chief Bond Strategist for series such as:
    CPIAUCSL   - CPI, all urban consumers
    PCEPILFE   - Core PCE
    GDP        - Gross Domestic Product
    UNRATE     - Unemployment rate
    DGS10      - 10-Year Treasury yield
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from core.data_source import DataSource, DataSourceError

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredConnector(DataSource):
    name = "FRED"
    default_ttl_seconds = 300  # per spec: economic calendar/series ~5 min

    def __init__(self, series_id: str, api_key: str, timeout: int = 10, limit: int = 5):
        self.series_id = series_id
        self.api_key = api_key
        self.timeout = timeout
        # Observations to fetch (newest-first). Default of 5 is right for
        # this platform's usual monthly/quarterly series (5 months/quarters
        # is a sensible trend window). A DAILY series needs a much wider
        # limit to cover the same real-world span — see
        # agents.chief_macro_officer.register_macro_data_sources()'s
        # per-series override for the Fed Funds Rate factor, which fetches
        # a daily target-range series specifically so a same-day FOMC move
        # is visible immediately rather than waiting for a monthly average.
        self.limit = limit

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        if not self.api_key:
            raise DataSourceError("FRED_API_KEY is not set")

        params = {
            "series_id": self.series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": self.limit,
        }
        try:
            resp = requests.get(FRED_BASE_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"FRED request failed for {self.series_id}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"FRED returned invalid JSON for {self.series_id}: {exc}") from exc

        observations = data.get("observations", [])
        if not observations:
            raise DataSourceError(f"FRED returned no observations for {self.series_id}")

        latest = observations[0]
        provider_ts = None
        try:
            provider_ts = datetime.strptime(latest["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            pass

        payload = {
            "series_id": self.series_id,
            "latest_value": latest.get("value"),
            "latest_date": latest.get("date"),
            "history": observations,
        }
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if "latest_value" not in payload or payload["latest_value"] in (None, ".", ""):
            return False
        return True
