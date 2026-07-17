# Architecture — Phase 1: Data Integrity & Refresh Manager

## Why this is Phase 1

The full platform spec has twelve analytical "Chief Officer" agents sitting
on top of live multi-asset data. All of them share one hard requirement:
**no agent may ever reason over stale, unvalidated, or unavailable data.**
Rather than re-implement that check twelve times (once per agent, with
twelve chances to get it subtly wrong), it's built once, centrally, here.
Every later phase depends on this module and nothing in this module depends
on anything later.

## The contract

```
Connector (DataSource)  --fetch()-->  DataIntegrityManager  --get()-->  Dataset
                                            |
                                            +-- caches within TTL
                                            +-- fails over to backups
                                            +-- scores quality (0-100)
                                            +-- logs every refresh
                                            +-- NEVER fabricates data
```

1. **`core.data_source.DataSource`** — abstract base every connector
   implements. A connector's only job is `fetch()` (raise `DataSourceError`
   on failure) and an optional `validate_shape()` sanity check. Connectors
   never decide freshness or quality — that's centralized so scoring is
   consistent no matter which of the ~30 planned data sources produced it.

2. **`core.dataset.Dataset`** — the mandatory metadata envelope. Every piece
   of data in the platform is wrapped in one before any agent sees it. Carries
   `source`, `time_collected`, `provider_timestamp`, `cache_expires_at`,
   `quality_score`, `validation_status`. The single gate agents must call is
   `dataset.is_usable()` — this is intentionally explicit rather than hidden
   behind exceptions, because "the data isn't fresh enough" is a routine,
   expected outcome an agent must handle gracefully (e.g. skip this analysis
   cycle), not a crash.

3. **`core.quality.score_quality`** — a small, deliberately transparent
   0-100 scoring function (50% freshness / 30% source tier / 20% shape
   validity). Institutional research needs every score to be explainable in
   one sentence, not a black box.

4. **`core.refresh_manager.DataIntegrityManager`** — the orchestrator.
   Register a named dataset with a primary connector and optional backups;
   `.get(key)` returns a cached `Dataset` if still within TTL, otherwise
   fetches fresh, tries backups on primary failure, scores and logs the
   result, and **always returns a `Dataset`** — even when every source fails,
   it returns a `MISSING`/`FAILED_VALIDATION` dataset rather than raising or
   silently returning `None`. This keeps "no data available" a normal,
   inspectable state rather than a special case.

## Why "always return a Dataset, never raise for staleness"

Two failure modes needed to be avoided:
- Agents silently working with `None` or stale data (the spec explicitly
  forbids this).
- Agents crashing on a routine, expected condition (a data source being
  temporarily down is normal in live markets, not exceptional).

`manager.get()` threads the needle: it always returns an object, and that
object always tells the truth about whether it's safe to use. For code paths
that *do* want fail-fast behavior (e.g. a scheduled job that should abort
loudly rather than proceed), `manager.get_or_raise()` is provided as a thin
wrapper that raises `StaleDataError`.

## What's demonstrated in Phase 1

- `connectors/fred_connector.py` — FRED macro series (needs a free API key)
- `connectors/cot_connector.py` — CFTC Commitment of Traders (no key needed)
- `connectors/yahoo_connector.py` — equity/futures prices via yfinance (no key needed)
- `scripts/demo_refresh.py` — wires all three into one `DataIntegrityManager`
  and prints the full fetch → validate → score → gate pipeline
- 22 passing unit/integration tests in `tests/`, using fake connectors to
  deterministically exercise: success, primary failure + backup failover,
  total failure (blocked), malformed payload (blocked), caching, force
  refresh, and the audit log

Note: this sandbox's network egress doesn't include `stlouisfed.org`,
`cftc.gov`, or `finance.yahoo.com`, so `demo_refresh.py` will show all three
as `MISSING` when run here — which is itself correct behavior (it proves the
manager blocks rather than fabricates data when sources are unreachable).
Once deployed anywhere with normal internet access, the same script will
show real live data flowing through with `VALID` status. Rely on the pytest
suite for network-independent proof of correctness.

## What's NOT in Phase 1 (coming later)

- The twelve Chief Officer agents (`agents/`)
- The Streamlit dashboard (`dashboard/`)
- Telegram alerting (`telegram/`)
- Persistence / the Chief Learning Officer's history store (`database/`)
- GitHub Actions *scheduled* data refresh jobs (CI for tests is included now;
  scheduled refresh workflows land once there's something for them to feed)
