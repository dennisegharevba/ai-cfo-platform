"""
SEC EDGAR connector — company fundamentals via the free XBRL companyconcept API.

Free, no API key required. SEC does require a descriptive User-Agent header
identifying the requester (see SEC_USER_AGENT in config/settings.py) —
requests without one are commonly rejected.

Docs: https://www.sec.gov/edgar/sec-api-documentation

Used by the Chief Equity Analyst for fundamentals such as:
    EarningsPerShareDiluted
    Revenues  (many filers switched to RevenueFromContractWithCustomerExcludingAssessedTax
               around 2018, when ASC 606 revenue recognition took effect — see
               fallback_concepts below, added after a live run showed exactly
               this: Apple's "Revenues" tag returned real, valid-looking data
               that was silently 8 YEARS STALE, because Apple stopped filing
               under that tag in 2018 and the connector had no way to notice
               a fresher tag existed. This is not a hypothetical: it happened
               on a real run, was mislabeled "valid" with quality_score 100.0,
               and would have fed a genuinely wrong "latest" revenue figure
               straight into Chief Equity Analyst's trend score.)

Returns data in the same {"latest_value", "latest_date", "history": [...]}
shape as FredConnector, so Chief Equity Analyst can reuse
agents.trend_scoring.series_trend_score directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

import requests

from core.data_source import DataSource, DataSourceError

EDGAR_BASE_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"

# Known revenue-tag migrations. Apple (and many other filers) moved from
# "Revenues" to one of these around the 2018 ASC 606 transition — a
# filer's OLD tag can keep returning a "successful," genuinely-looking
# real value indefinitely (the last thing ever filed under it), with no
# error to signal that a newer tag now holds the actually-current data.
# Passed as fallback_concepts wherever Revenue is registered.
REVENUE_FALLBACK_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]


def _period_days(entry: dict) -> Optional[int]:
    """Duration in days between an XBRL entry's "start" and "end" dates,
    or None if either is missing/unparseable. Used to distinguish a
    genuine 3-month quarterly figure from a 12-month annual one (or a
    6-month/9-month year-to-date figure) — form type (10-Q vs 10-K) alone
    isn't reliable for this, since both filing types can report multiple
    period lengths for the same concept."""
    start, end = entry.get("start"), entry.get("end")
    if not start or not end:
        return None
    try:
        return (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
    except ValueError:
        return None


class SecEdgarConnector(DataSource):
    name = "SEC_EDGAR"
    default_ttl_seconds = 60 * 60  # fundamentals update infrequently; hourly poll is plenty

    def __init__(
        self, cik: str, concept: str, user_agent: str, periods_history: int = 8, timeout: int = 15,
        fallback_concepts: Optional[List[str]] = None,
    ):
        """
        cik: the company's SEC CIK, e.g. "320193" for Apple Inc. (leading
             zeros are added automatically — no need to pre-pad to 10 digits).
        concept: a us-gaap XBRL tag, e.g. "EarningsPerShareDiluted", "Revenues".
        user_agent: REQUIRED by SEC — a descriptive string with contact info,
             e.g. "AI CFO Platform contact@example.com". Requests without a
             real contact string are commonly rejected or rate-limited harder.
        periods_history: how many of the most recent quarterly (10-Q) or
             annual (10-K) filings to keep for trend scoring.
        fallback_concepts: alternate XBRL tags to also try — e.g.
             REVENUE_FALLBACK_CONCEPTS for Revenue. Every concept (primary
             + fallbacks) that returns usable data is fetched, and
             whichever has the MOST RECENT filing date wins — not simply
             "first one that doesn't error," since a stale, abandoned tag
             can return successfully with real-looking but outdated data
             (see this module's docstring for exactly this happening live).
        """
        self.cik = str(cik).zfill(10)
        self.concept = concept
        self.fallback_concepts = list(fallback_concepts) if fallback_concepts else []
        self.user_agent = user_agent
        self.periods_history = max(periods_history, 2)
        self.timeout = timeout

    def fetch(self, **kwargs) -> tuple[Any, Optional[datetime]]:
        if not self.user_agent:
            raise DataSourceError("SEC_USER_AGENT is not set — SEC requires a descriptive User-Agent header")

        candidates = [self.concept] + self.fallback_concepts
        best_payload: Optional[dict] = None
        best_date: Optional[str] = None
        errors: List[str] = []

        for candidate_concept in candidates:
            try:
                payload = self._fetch_concept(candidate_concept)
            except DataSourceError as exc:
                errors.append(str(exc))
                continue
            candidate_date = payload.get("latest_date")
            # ISO "YYYY-MM-DD" strings compare correctly as plain strings.
            if candidate_date and (best_date is None or candidate_date > best_date):
                best_payload = payload
                best_date = candidate_date

        if best_payload is None:
            tried = ", ".join(candidates)
            raise DataSourceError(f"All XBRL concepts failed for CIK {self.cik} (tried: {tried}): {'; '.join(errors)}")

        provider_ts = None
        if best_date:
            try:
                provider_ts = datetime.strptime(best_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        return best_payload, provider_ts

    def _fetch_concept(self, concept: str) -> dict:
        """Fetches and parses ONE XBRL concept — the original single-tag
        logic, extracted so fetch() can try several and pick the best."""
        url = EDGAR_BASE_URL.format(cik=self.cik, concept=concept)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise DataSourceError(f"SEC EDGAR request failed for CIK {self.cik}/{concept}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"SEC EDGAR returned invalid JSON for CIK {self.cik}/{concept}: {exc}") from exc

        units = data.get("units", {})
        # Fundamentals are usually filed under "USD" or "USD/shares" — take whichever is present.
        entries = units.get("USD/shares") or units.get("USD") or []
        if not entries:
            raise DataSourceError(f"No '{concept}' data found for CIK {self.cik}")

        # Keep only actual quarterly/annual filings (10-Q, 10-K) with a value.
        filed = [e for e in entries if e.get("form") in ("10-Q", "10-K") and e.get("val") is not None]
        if not filed:
            raise DataSourceError(f"No 10-Q/10-K filings found for '{concept}' at CIK {self.cik}")

        # Deduplicate EXACT repeats (same start, end, and val) — found via
        # live testing to be a real, common feature of SEC's raw XBRL
        # feed (likely from multiple filings/amendments referencing the
        # same underlying fact), not a hypothetical edge case. Left
        # undeduplicated, repeats silently pad out the periods_history
        # window: with periods_history=8 and, say, 4 of the 8 slots
        # consumed by exact duplicates of the same 2 real quarters, the
        # "oldest in window" ends up being an actually-older, real quarter
        # than periods_history=8 was meant to reach — for a seasonal
        # business, this can mean comparing a naturally-high quarter
        # (e.g. the holiday quarter) against a naturally-lower one,
        # producing a large "trend" that's really just normal seasonal
        # variation, not a genuine business change. Confirmed directly: a
        # live run's raw Apple EPS data reconstructed here produces
        # exactly this — a -15.8% "decline" that clamped to -100.0,
        # comparing Q1 FY2025 ($2.40, the holiday quarter) against Q3
        # FY2026 ($2.02, the summer quarter) purely because 4 duplicate
        # entries had consumed half the 8-slot window.
        seen = set()
        deduped = []
        for e in filed:
            key = (e.get("start"), e.get("end"), e.get("val"))
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        filed = deduped

        # Filter to a SINGLE, CONSISTENT reporting period length. Revenue
        # and EPS are XBRL "duration" facts — filtering by form type alone
        # (10-Q vs 10-K) is NOT enough to guarantee comparable periods: a
        # 10-K commonly includes quarterly comparative figures alongside
        # the annual total, and a 10-Q sometimes reports 6-month/9-month
        # year-to-date cumulative figures alongside the standalone
        # quarter. Mixing period lengths in one "trend" series means
        # comparing e.g. one quarter's EPS against a full year's EPS —
        # a huge, meaningless swing driven entirely by reporting-period
        # length, not real business performance, and a real, reproducible
        # cause of clamped/extreme scores found via live testing (see
        # docs/ARCHITECTURE_SEC_STALE_REVENUE_FIX.md). Quarterly (~90 day)
        # periods are preferred when there are enough for a real trend —
        # more frequent, more granular data — falling back to annual
        # (~365 day) periods otherwise. Entries with unparseable or
        # in-between period lengths (6-month/9-month YTD) are excluded
        # entirely rather than guessed into either bucket.
        with_period_days = [(e, _period_days(e)) for e in filed]
        quarterly = [e for e, days in with_period_days if days is not None and 80 <= days <= 100]
        annual = [e for e, days in with_period_days if days is not None and 350 <= days <= 380]
        consistent_period = quarterly if len(quarterly) >= 2 else annual
        if not consistent_period:
            raise DataSourceError(
                f"No consistent-period (quarterly or annual) filings found for '{concept}' at CIK {self.cik} "
                f"— {len(filed)} filing(s) found, but none formed a comparable same-length series"
            )

        consistent_period.sort(key=lambda e: e.get("end", ""), reverse=True)
        consistent_period = consistent_period[: self.periods_history]

        history = [{"value": e["val"], "date": e.get("end"), "form": e.get("form")} for e in consistent_period]
        latest = history[0]

        return {
            "cik": self.cik,
            "concept": concept,
            "latest_value": latest["value"],
            "latest_date": latest["date"],
            "history": history,
        }

    def validate_shape(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("latest_value") is None:
            return False
        return isinstance(payload.get("history"), list) and len(payload["history"]) > 0
