from unittest.mock import patch, MagicMock

import pytest

from connectors.sec_edgar_connector import SecEdgarConnector
from core.data_source import DataSourceError


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _companyconcept_payload(entries):
    return {"units": {"USD/shares": entries}}


# --- fallback_concepts: the stale-tag bug found via live testing ---

def _mock_get_by_concept(concept_to_entries):
    """Returns a requests.get replacement that inspects the URL to decide
    which concept's fake entries to return — simulating SEC EDGAR
    returning DIFFERENT data depending on which XBRL tag is queried."""
    def _fake_get(url, headers=None, timeout=None):
        for concept, entries in concept_to_entries.items():
            if f"/{concept}.json" in url:
                return _mock_response(_companyconcept_payload(entries))
        return _mock_response({"units": {}})
    return _fake_get


def test_fallback_concept_wins_when_it_has_more_recent_data():
    """
    Direct regression test for the exact bug found via live testing:
    Apple's "Revenues" XBRL tag returns REAL, successfully-parsing data
    (not empty, not an error) but from 2018 — because Apple stopped
    filing under that tag around the 2018 ASC 606 transition. The
    fallback concept has genuinely newer data and must win, not just
    "whichever succeeds first."
    """
    stale_primary = [{"val": 265595000000, "start": "2017-09-30", "end": "2018-09-29", "form": "10-K"}]
    fresh_fallback = [{"val": 391035000000, "start": "2025-06-28", "end": "2026-06-27", "form": "10-K"}]

    with patch(
        "connectors.sec_edgar_connector.requests.get",
        side_effect=_mock_get_by_concept({
            "Revenues": stale_primary,
            "RevenueFromContractWithCustomerExcludingAssessedTax": fresh_fallback,
        }),
    ):
        connector = SecEdgarConnector(
            cik="320193", concept="Revenues", user_agent="Test test@example.com",
            fallback_concepts=["RevenueFromContractWithCustomerExcludingAssessedTax"],
        )
        payload, provider_ts = connector.fetch()

    assert payload["latest_date"] == "2026-06-27"  # NOT the stale 2018-09-29
    assert payload["latest_value"] == 391035000000
    assert payload["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_primary_concept_wins_when_it_is_genuinely_the_freshest():
    """The multi-candidate logic must not blindly prefer fallbacks either
    — for a filer that never migrated tags, the primary concept (with
    genuinely fresher data than an unused fallback) should still win."""
    fresh_primary = [
        {"val": 100.0, "start": "2026-04-01", "end": "2026-06-30", "form": "10-Q"},
        {"val": 95.0, "start": "2026-01-01", "end": "2026-03-31", "form": "10-Q"},
    ]
    empty_fallback = []  # fallback tag was never used by this filer

    with patch(
        "connectors.sec_edgar_connector.requests.get",
        side_effect=_mock_get_by_concept({
            "Revenues": fresh_primary,
            "RevenueFromContractWithCustomerExcludingAssessedTax": empty_fallback,
        }),
    ):
        connector = SecEdgarConnector(
            cik="1", concept="Revenues", user_agent="Test test@example.com",
            fallback_concepts=["RevenueFromContractWithCustomerExcludingAssessedTax"],
        )
        payload, provider_ts = connector.fetch()

    assert payload["latest_date"] == "2026-06-30"
    assert payload["concept"] == "Revenues"


def test_no_fallback_concepts_behaves_exactly_as_before():
    """Backward compatibility: a connector with no fallback_concepts
    (e.g. EPS, which doesn't have this tag-migration problem) behaves
    identically to the original single-tag implementation."""
    entries = [
        {"val": 1.50, "start": "2026-01-01", "end": "2026-03-31", "form": "10-Q"},
        {"val": 1.40, "start": "2025-10-01", "end": "2025-12-31", "form": "10-Q"},
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    assert payload["latest_value"] == 1.50
    assert payload["concept"] == "EarningsPerShareDiluted"


def test_raises_only_when_every_candidate_fails():
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response({"units": {}})):
        connector = SecEdgarConnector(
            cik="1", concept="Revenues", user_agent="Test test@example.com",
            fallback_concepts=["RevenueFromContractWithCustomerExcludingAssessedTax"],
        )
        with pytest.raises(DataSourceError, match="All XBRL concepts failed"):
            connector.fetch()


def test_revenue_fallback_concepts_constant_is_available_for_reuse():
    from connectors.sec_edgar_connector import REVENUE_FALLBACK_CONCEPTS
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in REVENUE_FALLBACK_CONCEPTS


# --- deduplication: the bug found from the user's own live diagnostic run ---

def test_exact_duplicate_entries_are_deduplicated_not_double_counted():
    """
    Direct regression test for a real bug found via the user's own live
    diagnostic run (scripts/debug_sec_edgar_raw.py against real Apple
    data): SEC's raw feed genuinely contains exact duplicate entries
    (same start/end/val, likely from multiple filings/amendments
    referencing the same fact). Left undeduplicated, repeats silently
    padded out the periods_history window — pushing a genuinely older
    quarter out and pulling in a seasonally mismatched one. Confirmed on
    the user's real data: Apple's Q1 FY2025 EPS ($2.40, the holiday
    quarter) ended up compared against Q3 FY2026 ($2.02, the summer
    quarter) purely because 4 duplicate rows had consumed half the
    8-slot window — a -15.8% "decline" that was really just normal
    seasonal variation, not a real business change, and clamped the
    overall bias to exactly -100.0.

    This test reproduces that exact scenario with real duplicate entries
    plus 2 more genuinely distinct entries reaching further back — proven
    directly that after deduplication, the window correctly reaches 7
    DISTINCT quarters instead of stopping early at a duplicate-padded 8th
    slot that was really only the 5th distinct quarter.
    """
    entries = [
        {"val": 2.02, "start": "2026-03-29", "end": "2026-06-27", "form": "10-Q"},
        {"val": 2.01, "start": "2025-12-28", "end": "2026-03-28", "form": "10-Q"},
        {"val": 2.84, "start": "2025-09-28", "end": "2025-12-27", "form": "10-Q"},
        {"val": 1.57, "start": "2025-03-30", "end": "2025-06-28", "form": "10-Q"},
        {"val": 1.57, "start": "2025-03-30", "end": "2025-06-28", "form": "10-Q"},  # real duplicate
        {"val": 1.65, "start": "2024-12-29", "end": "2025-03-29", "form": "10-Q"},
        {"val": 1.65, "start": "2024-12-29", "end": "2025-03-29", "form": "10-Q"},  # real duplicate
        {"val": 2.40, "start": "2024-09-29", "end": "2024-12-28", "form": "10-Q"},
        {"val": 2.40, "start": "2024-09-29", "end": "2024-12-28", "form": "10-Q"},  # real duplicate
        {"val": 1.53, "start": "2023-12-31", "end": "2024-03-30", "form": "10-Q"},  # genuinely further back
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    # 7 DISTINCT quarters, not 8 slots half-consumed by duplicates.
    assert len(payload["history"]) == 7
    oldest = payload["history"][-1]["value"]
    newest = payload["history"][0]["value"]
    assert oldest == 1.53  # the genuinely-further-back entry, not the duplicate-padded 2024-12-28 one
    # A real, sensible positive trend — not the seasonally-mismatched
    # -15.8% "decline" the undeduplicated version produced.
    assert newest > oldest


def test_duplicates_across_different_periods_dont_interfere_with_each_other():
    """Two DIFFERENT quarters, each appearing twice, should collapse to
    exactly 2 distinct entries — not 4, and not accidentally merged into 1."""
    entries = [
        {"val": 2.02, "start": "2026-03-29", "end": "2026-06-27", "form": "10-Q"},
        {"val": 2.02, "start": "2026-03-29", "end": "2026-06-27", "form": "10-Q"},
        {"val": 2.01, "start": "2025-12-28", "end": "2026-03-28", "form": "10-Q"},
        {"val": 2.01, "start": "2025-12-28", "end": "2026-03-28", "form": "10-Q"},
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()
    assert len(payload["history"]) == 2


def test_fetch_filters_to_10q_10k_and_sorts_newest_first():
    entries = [
        {"val": 1.50, "start": "2026-01-01", "end": "2026-03-31", "form": "10-Q"},
        {"val": 1.20, "start": "2025-10-01", "end": "2025-12-31", "form": "10-Q"},
        {"val": 6.00, "start": "2025-04-01", "end": "2026-03-31", "form": "10-K"},  # annual — different period length, correctly excluded from the quarterly series
        {"val": 999, "start": "2025-12-31", "end": "2026-01-01", "form": "8-K"},  # wrong form entirely — should be excluded
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    assert payload["latest_value"] == 1.50
    assert payload["latest_date"] == "2026-03-31"
    assert len(payload["history"]) == 2  # only the 2 quarterly entries — 10-K and 8-K both excluded
    assert provider_ts.year == 2026 and provider_ts.month == 3


def test_fetch_falls_back_to_annual_when_fewer_than_2_quarterly_periods_exist():
    """A filer with only one quarterly data point (not enough to form a
    trend) but multiple annual filings should fall back to the annual
    series, not fail outright."""
    entries = [
        {"val": 1.50, "start": "2026-01-01", "end": "2026-03-31", "form": "10-Q"},  # only 1 quarterly — insufficient
        {"val": 6.00, "start": "2025-04-01", "end": "2026-03-31", "form": "10-K"},
        {"val": 5.50, "start": "2024-04-01", "end": "2025-03-31", "form": "10-K"},
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    assert len(payload["history"]) == 2  # the 2 annual entries
    assert payload["latest_value"] == 6.00


def test_fetch_gracefully_returns_a_single_entry_when_theres_not_enough_for_a_trend():
    """
    A single quarterly entry alongside a single annual entry (no other
    data) can't form a 2-point trend in either bucket — but the connector
    itself doesn't need to enforce a minimum of 2; agents.trend_scoring's
    percent_change_score already returns None gracefully for a
    single-point history. The connector's job is just to return a
    genuinely comparable, same-period-length series, however short.
    """
    entries = [
        {"val": 1.50, "start": "2026-01-01", "end": "2026-03-31", "form": "10-Q"},
        {"val": 6.00, "start": "2025-04-01", "end": "2026-03-31", "form": "10-K"},
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        payload, provider_ts = connector.fetch()

    # Only 1 quarterly entry exists (insufficient), so it falls back to
    # the 1 annual entry — a single, real, same-period-length data point.
    assert len(payload["history"]) == 1
    assert payload["latest_value"] == 6.00


def test_fetch_raises_when_no_period_length_can_be_determined_at_all():
    """The genuine failure case: every entry is missing "start" (or has
    unparseable dates), so period length can't be computed for ANY
    entry — neither the quarterly nor annual bucket gets anything."""
    entries = [
        {"val": 1.50, "end": "2026-03-31", "form": "10-Q"},  # no "start" at all
        {"val": 6.00, "end": "2026-03-31", "form": "10-K"},  # no "start" at all
    ]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent="Test test@example.com")
        with pytest.raises(DataSourceError, match="No consistent-period"):
            connector.fetch()


def test_cik_is_zero_padded():
    connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
    assert connector.cik == "0000320193"


def test_missing_user_agent_raises_before_any_request():
    connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="")
    with pytest.raises(DataSourceError):
        connector.fetch()


def test_no_matching_filings_raises():
    entries = [{"val": 999, "end": "2026-01-01", "form": "8-K"}]
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response(_companyconcept_payload(entries))):
        connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_empty_units_raises():
    with patch("connectors.sec_edgar_connector.requests.get",
               return_value=_mock_response({"units": {}})):
        connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
        with pytest.raises(DataSourceError):
            connector.fetch()


def test_validate_shape():
    connector = SecEdgarConnector(cik="320193", concept="Revenues", user_agent="Test test@example.com")
    assert connector.validate_shape({"latest_value": 1.5, "history": [{"value": 1.5}]}) is True
    assert connector.validate_shape({"latest_value": None, "history": []}) is False
    assert connector.validate_shape({"latest_value": 1.5, "history": []}) is False
