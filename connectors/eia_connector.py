"""
EIA (U.S. Energy Information Administration) connector — free, public API
(https://www.eia.gov/opendata/), requires a free API key (same
"sign up, paste into .env" pattern as FRED).

Used by agents/chief_commodity_fundamentals_officer.py for real supply/
demand data — specifically inventory/storage levels, which per the
Institutional Fundamental Scoring Engine upgrade spec are two of the
concrete "Commodity Fundamentals" line items this platform can actually
back with a real free live source (most of that section's other line
items — mine production, central bank buying, jewellery demand, shipping,
storage COST, etc. — have no free structured API available and are
deliberately skipped rather than faked; see
docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md).

Returns the same {"latest_value", "latest_date", "history": [...]} shape
as connectors.fred_connector.FredConnector, so
agents.trend_scoring.series_trend_score works on EIA data with zero
changes — no new scoring math needed for this connector.

HONEST CAVEAT — same pattern as config/cftc_markets.py and
config/sp500_tickers.py: the EIA v2 API's exact route path and facet
parameter names (`route`/`facets` below) could not be verified against a
live query from this development environment (no network access here).
The values used in agents/chief_commodity_fundamentals_officer.py are a
best-effort reading of EIA's v2 API documentation structure, not a
verified-live configuration. Before relying on this, check the actual
route/facets for your series at https://www.eia.gov/opendata/browser/ —
a wrong route/facet combination fails safely (DataSourceError, handled
exactly like every other connector failure in this platform: the affected
factor is excluded, never fabricated), it does not silently return wrong
data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from core.data_source import DataSource, DataSourceError

EIA_BASE_URL = "https://api.eia.gov/v2"


class EiaConnector(DataSource):
    name = "EIA"
    default_ttl_seconds = 60 * 60  # per the original spec: "EIA immediately after release" — hourly poll is a reasonable default absent an event-driven trigger

    def __init__(
        self, route: str, facets: Dict[str, List[str]], api_key: str,
        frequency: str = "weekly", data_column: str = "value",
        periods_history: int = 12, timeout: int = 15,
    ):
        """
        route: EIA v2 API route path, e.g. "petroleum/stoc/wstk" (Weekly
            petroleum stocks) or "natural-gas/stor/wkly" (Weekly natural
            gas storage) — see module docstring's caveat about verifying
            this against EIA's own API browser.
        facets: EIA v2 facet filters, e.g. {"product": ["EPC0"], "duoarea": ["NUS"]}
            for "Crude Oil, U.S." — again, verify against the live API browser.
        """
        self.route = route.strip("/")
        self.facets = facets
        self.api_key = api_key
        self.frequency = frequency
        self.data_column = data_column
        self.periods_history = max(periods_history, 2)
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        if not self.api_key:
            raise DataSourceError("EIA_API_KEY is not set")

        params: Dict[str, Any] = {
            "api_key": self.api_key,
            "frequency": self.frequency,
            "data[0]": self.data_column,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": self.periods_history,
        }
        for facet_key, facet_values in self.facets.items():
            for i, value in enumerate(facet_values):
                params[f"facets[{facet_key}][{i}]"] = value

        url = f"{EIA_BASE_URL}/{self.route}/data/"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"EIA request failed for route '{self.route}': {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"EIA returned invalid JSON for route '{self.route}': {exc}") from exc

        rows = payload.get("response", {}).get("data", [])
        if not rows:
            raise DataSourceError(f"EIA returned no data for route '{self.route}' with facets {self.facets}")

        # EIA v2 already sorts by our requested sort params (period desc),
        # but don't rely on that silently — sort defensively so this
        # connector's newest-first guarantee holds even if that changes.
        def _row_period(row: dict) -> str:
            return str(row.get("period", ""))

        rows = sorted(rows, key=_row_period, reverse=True)

        history = []
        for row in rows:
            value = row.get(self.data_column)
            if value is None:
                continue
            history.append({"value": value, "date": row.get("period")})

        if not history:
            raise DataSourceError(f"EIA rows for route '{self.route}' had no usable '{self.data_column}' values")

        latest = history[0]
        provider_ts = None
        if latest.get("date"):
            for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    provider_ts = datetime.strptime(latest["date"], fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

        payload_out = {
            "route": self.route,
            "latest_value": latest["value"],
            "latest_date": latest["date"],
            "history": history,
        }
        return payload_out, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("latest_value") is None:
            return False
        return isinstance(payload.get("history"), list) and len(payload["history"]) > 0
