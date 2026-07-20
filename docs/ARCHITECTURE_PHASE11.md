# Architecture — Phase 11: GitHub Actions Scheduled Automation

## The last phase on the original roadmap

Phases 1-9 built the twelve Chief Officers. Phase 10 gave them a dashboard.
Phase 11 is the last piece: running the whole pipeline **unattended, on a
schedule**, instead of via manual demo scripts or dashboard clicks.

## `config/watchlist.py` — what the automated cycle covers

A plain list of `{"asset_or_theme": ..., "departments": {...}}` entries.
Editing what the scheduled job covers is a config change, not a code
change — add an entry, pick which department keys apply, done.

## `scripts/run_daily_cycle.py` — the production entry point

This is the same pattern every Phase 2-9 demo script used (register
connectors, run departments, synthesize, persist, evaluate for alerting)
but refactored into something genuinely re-runnable unattended:

```
run_cycle(watchlist, manager, learning_officer, execution_officer)
    for each watchlist entry:
        try:
            run each configured department  -> AgentReport, record each via ChiefLearningOfficer
            ChiefStrategyOfficer.synthesize() -> StrategyReport, record via ChiefLearningOfficer
            ChiefExecutionOfficer.process()   -> alerts if it clears the gate
            append a summary result
        except Exception:
            log it, append an error result, CONTINUE to the next entry
    return per-asset summaries
```

**Per-asset isolation is the key design decision here.** Every prior
phase's data-integrity work protects against ONE department using bad
data; this protects against ONE asset's processing taking down the entire
scheduled run. A cycle where 4 of 5 watchlist entries succeed and 1 logs
an error is a normal, useful outcome — not something that should show up
as a failed GitHub Actions run. Only a genuine bug that somehow escapes
that per-entry try/except (e.g. in `run_cycle` itself, or a `ReportStore`
failure) would actually fail the job, which is the correct signal: a data
source being briefly unreachable is routine; the orchestration code itself
throwing is not.

The department-dispatch functions (`_run_macro`, `_run_bond`, etc.) are
deliberately thin — each just registers its connector(s) if not already
present (reusing `DataIntegrityManager.is_registered()` from Phase 10) and
calls the exact same agent classes every earlier phase's demo script uses.
`DEPARTMENT_RUNNERS` maps watchlist department keys to these functions, so
`run_cycle` itself has no hardcoded knowledge of which departments exist.

## The GitHub Actions workflow (`.github/workflows/scheduled_run.yml`)

A **second** workflow file, separate from `ci.yml` (which still runs the
test suite on every push). This one:

- Triggers on a cron schedule (`0 13 * * 1-5` — weekdays, 13:00 UTC) AND
  `workflow_dispatch`, so it can also be triggered manually from the
  Actions tab for testing without waiting for the schedule
- Reads `FRED_API_KEY`, `SEC_USER_AGENT`, `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID` from GitHub Actions **secrets** (Settings → Secrets
  and variables → Actions), never committed to the repo
- Runs `scripts/run_daily_cycle.py`
- Persists `ai_cfo_platform.db` and also uploads it as a downloadable
  build artifact (30-day retention)

## Persisting SQLite across ephemeral runners — the honest tradeoff

GitHub Actions runners are thrown away after every job — anything written
to disk during a run is gone unless explicitly saved somewhere.
`actions/cache` is the free option, but it comes with a real wrinkle worth
being upfront about: **cache keys are immutable once written** — there is
no "overwrite this cache entry" operation. So this workflow:

1. **Restores** using `restore-keys: ai-cfo-db-` (a prefix match), which
   finds the most recent previous run's cache entry regardless of its
   exact run ID
2. **Saves** under a brand-new key (`ai-cfo-db-${{ github.run_id }}`,
   unique every run), which always succeeds since it's never been used before

The practical effect: the database DOES accumulate across runs (each run
restores yesterday's data, adds today's, saves it under a new key), but it
also leaves behind a growing number of cache entries over time. GitHub
evicts old caches automatically (7-day inactivity, or the repo's 10GB
cache budget), so this isn't unbounded, but it's genuinely a lightweight
mechanism suited to this project's current demo/personal-use scale — **a
real production deployment should replace this with a persistent external
database** (a small hosted Postgres/SQLite-on-a-volume, etc.) rather than
relying on CI cache as a database. Documenting this tradeoff honestly here
rather than presenting the cache-based approach as if it were
production-grade infrastructure.

## What's demonstrated in Phase 11

- `scripts/run_daily_cycle.py` run manually in this sandbox (no network):
  all 5 watchlist entries processed cleanly with degraded/zero-confidence
  results and no crashes — exactly the same graceful-degradation behavior
  every prior phase's demo scripts already established, now proven at the
  orchestration level too
- 5 new tests (225 total): a full successful cycle recorded end-to-end
  against fake sources, one asset's processing genuinely blowing up
  (`RuntimeError`) while a second, unrelated asset in the same cycle still
  processes successfully afterward, an unknown department key being
  skipped rather than fatal, an empty watchlist, and a sanity check that
  every department key actually used in `config/watchlist.py` has a real
  handler (catching a config typo here rather than in a live scheduled run)

## What's NOT in Phase 11

This completes every phase on the original roadmap. Natural extensions
beyond the original spec, not built here:
- Wiring `ExecutionDecision`s from the scheduled run into the Learning
  Officer's persistence automatically (both exist; not yet connected)
- A real external database backing `ReportStore`, replacing the
  CI-cache-based persistence described above
- Feeding `ChiefLearningOfficer`'s accumulated performance analytics back
  into `ChiefStrategyOfficer`'s department weights (the spec's "improve
  future scoring" — Phase 8 already stores and reports the data that would
  inform this)
