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

from datetime import date, datetime, timezone
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


def fetch_cot_history_range(
    market_and_exchange_name: str, start_date: date, end_date: date, timeout: int = 15, limit: int = 5000,
) -> Optional[list]:
    """
    Backtesting-only bulk historical fetch — every weekly report between
    start_date and end_date (inclusive), OLDEST FIRST, for one CFTC
    market. Distinct from CotConnector above (the live DataSource, which
    only ever fetches the most recent `weeks_history` reports): a genuine
    historical backtest needs the full multi-year archive, which the same
    CFTC Socrata endpoint supports via a date-range `$where` clause — this
    was flagged as unbuilt in agents/backtest_signals.py's own docstring
    ("CFTC-based Commodity/FX Analyst — would need extending
    connectors/cot_connector.py to fetch a wide historical date range...
    but it's unbuilt"); this function is that extension. See
    agents/swing_signal_backtest.py for what uses it.

    No point-in-time/vintage concern here, unlike
    connectors/fred_historical.py's fetch_point_in_time_history — a COT
    report is a single snapshot published once and never revised after
    the fact, so this is a plain historical range query, not a
    vintage-correct one.

    limit=5000 is a generous ceiling (weekly data over 10 years is ~520
    rows for a single market) rather than a value ever expected to be hit
    — if it ever is, results would silently truncate, so it's set well
    above any realistic real-world range instead of tuned tightly.

    Returns None (never raises) on any failure — missing data, a network
    error, a malformed response — matching
    connectors/fred_historical.py's "never fabricate, degrade gracefully"
    convention for backtest-only helpers. This deliberately differs from
    CotConnector.fetch() above, which DOES raise DataSourceError — that
    one feeds core.DataIntegrityManager's live failure-tracking, which
    needs a raised exception to register a failed source; this one feeds
    a backtest loop, which just needs to skip cleanly.
    """
    where = (
        f"market_and_exchange_names='{market_and_exchange_name}' AND "
        f"report_date_as_yyyy_mm_dd >= '{start_date.isoformat()}' AND "
        f"report_date_as_yyyy_mm_dd <= '{end_date.isoformat()}'"
    )
    params = {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": limit,
    }
    try:
        resp = requests.get(COT_BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
    except (requests.RequestException, ValueError):
        return None

    if not rows:
        return None

    return [_row_to_snapshot(row) for row in rows]
