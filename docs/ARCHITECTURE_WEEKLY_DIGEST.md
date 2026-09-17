# Weekly sentiment digest

## What this adds

A weekly summary view of the Chief Sentiment Officer's saved reports:
how many days were bullish/bearish/neutral, the average bias and
confidence over the week, and the most-repeated catalysts and risks
across the whole period — rather than only ever seeing the latest
single snapshot.

## How it actually gets data — an honest, important dependency

`agents/news_digest.py`'s `build_weekly_sentiment_digest()` aggregates
whatever Chief Sentiment Officer reports are already saved in
`database/report_store.py`'s `ReportStore` — it doesn't fetch or
generate anything new itself.

**This platform already has a real mechanism that populates this
history over time**: `.github/workflows/scheduled_run.yml` runs a
research cycle on weekdays, and `scripts/run_daily_cycle.py` persists
every department's report (via `ChiefLearningOfficer.record_report()`).
Clicking "Run Chief Sentiment Officer" interactively on the dashboard
does **not** save to the store — it only shows the result for that
session, matching its existing, established design. This means the
digest will show "no data yet" on a fresh install, or on a server where
nothing has been writing to `ai_cfo_platform.db` regularly — it needs
real, accumulated history to summarize, and manufacturing one from a
single click would misrepresent what actually happened.

**Practical implication**: if you want the digest to be meaningfully
populated on your deployed dashboard specifically (not just wherever
GitHub Actions' own ephemeral runner writes its cache), something needs
to be writing to that same `ai_cfo_platform.db` file on the same server
the dashboard reads from — for example, a `scripts/run_daily_cycle.py`
cron job on your DigitalOcean droplet, the same way `risk-monitor`
already runs continuously there. Not built as part of this delivery;
worth doing as a deliberate next step if you want this genuinely useful
day to day.

## What was added to make this possible

`database/report_store.py`'s `get_agent_reports()` gained an optional
`since` parameter — a plain `limit` can't correctly express "everything
from the last 7 days" (it would silently cut off older reports within
the window if more than `limit` were recorded that week).

## Dashboard integration

The Sentiment section of Department Reports now shows the digest
directly below the existing single-report view — report count, average
bias/confidence, a day-count breakdown by bias, and the top repeated
catalysts/risks for the week. Shows a clear, honest "no data yet"
message rather than an empty or broken-looking display when there's
nothing to summarize.

## Testing

8 tests in `tests/test_news_digest.py` (empty input, date-range
correctness, averaging, deduplication, `top_n`, missing-field
robustness), 3 in `tests/test_report_store.py` for the new `since`
filter, and 2 dashboard tests — one confirming the honest empty-state
message, and one that seeds the actual on-disk database with real
reports and confirms the displayed metrics genuinely reflect that data,
not just that the page doesn't crash.
