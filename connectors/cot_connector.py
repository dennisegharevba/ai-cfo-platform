"""
CFTC Commitment of Traders (COT) connector.

Free, no API key required. Uses the CFTC's public Socrata Open Data endpoint
for the Legacy Futures-Only report.

Used by the Chief Commodity Analyst / Chief FX Analyst for positioning data.
COT is published weekly (Fridays, 3:30pm ET) — the platform should refresh
this immediately after publication (see config/refresh_intervals.py) rather
than polling constantly.

Phase 3 update: fetches a multi-week window (not just the latest report) so
agents can score positioning *trend*, not just a single snapshot — mirrors
the FRED connector's `history` shape so agents can share scoring patterns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from core.data_source import DataSource, DataSourceError

# CFTC Socrata dataset: Commitment of Traders - Futures Only Legacy Report
COT_BASE_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"


def _row_to_snapshot(row: dict) -> dict:
    """Extract the fields agents care about from one raw CFTC row."""
    return {
        "report_date": row.get("report_date_as_yyyy_mm_dd"),
        "noncomm_long": row.get("noncomm_positions_long_all"),
        "noncomm_short": row.get("noncomm_positions_short_all"),
        "comm_long": row.get("comm_positions_long_all"),
        "comm_short": row.get("comm_positions_short_all"),
        "open_interest": row.get("open_interest_all"),
    }


class CotConnector(DataSource):
    name = "CFTC_COT"
    default_ttl_seconds = 60 * 60 * 24 * 7  # weekly report; refresh manager can force-refresh on publish day

    def __init__(self, market_and_exchange_name: str, weeks_history: int = 8, timeout: int = 15):
        """
        market_and_exchange_name: exact CFTC market name, e.g.
            "GOLD - COMMODITY EXCHANGE INC."
            "WTI FINANCIAL CRUDE OIL - NEW YORK MERCANTILE EXCHANGE"
            "EURO FX - CHICAGO MERCANTILE EXCHANGE"
        weeks_history: how many of the most recent weekly reports to fetch,
            so agents can score positioning trend rather than a single
            snapshot. Minimum useful value is 2.
        """
        self.market_name = market_and_exchange_name
        self.weeks_history = max(weeks_history, 2)
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        params = {
            "$where": f"market_and_exchange_names='{self.market_name}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": self.weeks_history,
        }
        try:
            resp = requests.get(COT_BASE_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            rows = resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"CFTC COT request failed for {self.market_name}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"CFTC COT returned invalid JSON: {exc}") from exc

        if not rows:
            raise DataSourceError(f"No COT rows returned for market '{self.market_name}'")

        # rows are already newest-first per $order above
        history = [_row_to_snapshot(row) for row in rows]
        latest = history[0]

        provider_ts = None
        date_str = latest.get("report_date")
        if date_str:
            try:
                provider_ts = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        payload = {
            "market": self.market_name,
            "report_date": latest.get("report_date"),
            "noncomm_long": latest.get("noncomm_long"),
            "noncomm_short": latest.get("noncomm_short"),
            "comm_long": latest.get("comm_long"),
            "comm_short": latest.get("comm_short"),
            "open_interest": latest.get("open_interest"),
            "history": history,  # newest first, same shape as `latest`
        }
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        required = ("noncomm_long", "noncomm_short", "open_interest")
        if not all(payload.get(k) is not None for k in required):
            return False
        return isinstance(payload.get("history"), list) and len(payload["history"]) > 0
