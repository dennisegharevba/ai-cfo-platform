"""
SEC EDGAR connector — company fundamentals via the free XBRL companyconcept API.

Free, no API key required. SEC does require a descriptive User-Agent header
identifying the requester (see SEC_USER_AGENT in config/settings.py) —
requests without one are commonly rejected.

Docs: https://www.sec.gov/edgar/sec-api-documentation

Used by the Chief Equity Analyst for fundamentals such as:
    EarningsPerShareDiluted
    Revenues  (some filers use RevenueFromContractWithCustomerExcludingAssessedTax instead —
               check a company's actual filings if this tag comes back empty)

Returns data in the same {"latest_value", "latest_date", "history": [...]}
shape as FredConnector, so Chief Equity Analyst can reuse
agents.trend_scoring.series_trend_score directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from core.data_source import DataSource, DataSourceError

EDGAR_BASE_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"


class SecEdgarConnector(DataSource):
    name = "SEC_EDGAR"
    default_ttl_seconds = 60 * 60  # fundamentals update infrequently; hourly poll is plenty

    def __init__(self, cik: str, concept: str, user_agent: str, periods_history: int = 8, timeout: int = 15):
        """
        cik: the company's SEC CIK, e.g. "320193" for Apple Inc. (leading
             zeros are added automatically — no need to pre-pad to 10 digits).
        concept: a us-gaap XBRL tag, e.g. "EarningsPerShareDiluted", "Revenues".
        user_agent: REQUIRED by SEC — a descriptive string with contact info,
             e.g. "AI CFO Platform contact@example.com". Requests without a
             real contact string are commonly rejected or rate-limited harder.
        periods_history: how many of the most recent quarterly (10-Q) or
             annual (10-K) filings to keep for trend scoring.
        """
        self.cik = str(cik).zfill(10)
        self.concept = concept
        self.user_agent = user_agent
        self.periods_history = max(periods_history, 2)
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        if not self.user_agent:
            raise DataSourceError("SEC_USER_AGENT is not set — SEC requires a descriptive User-Agent header")

        url = EDGAR_BASE_URL.format(cik=self.cik, concept=self.concept)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"SEC EDGAR request failed for CIK {self.cik}/{self.concept}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"SEC EDGAR returned invalid JSON for CIK {self.cik}/{self.concept}: {exc}") from exc

        units = data.get("units", {})
        # Fundamentals are usually filed under "USD" or "USD/shares" — take whichever is present.
        entries = units.get("USD/shares") or units.get("USD") or []
        if not entries:
            raise DataSourceError(f"No '{self.concept}' data found for CIK {self.cik}")

        # Keep only actual quarterly/annual filings (10-Q, 10-K), most recent period-end first.
        filed = [e for e in entries if e.get("form") in ("10-Q", "10-K") and e.get("val") is not None]
        if not filed:
            raise DataSourceError(f"No 10-Q/10-K filings found for '{self.concept}' at CIK {self.cik}")

        filed.sort(key=lambda e: e.get("end", ""), reverse=True)
        filed = filed[: self.periods_history]

        history = [{"value": e["val"], "date": e.get("end"), "form": e.get("form")} for e in filed]
        latest = history[0]

        provider_ts = None
        if latest.get("date"):
            try:
                provider_ts = datetime.strptime(latest["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        payload = {
            "cik": self.cik,
            "concept": self.concept,
            "latest_value": latest["value"],
            "latest_date": latest["date"],
            "history": history,
        }
        return payload, provider_ts

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("latest_value") is None:
            return False
        return isinstance(payload.get("history"), list) and len(payload["history"]) > 0
