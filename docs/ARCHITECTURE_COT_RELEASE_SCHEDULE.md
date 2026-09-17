# COT release schedule awareness

## What this replaces

`config/refresh_intervals.py` has long had an explicit, acknowledged gap
in its own comment: `"cot_report": 60 * 60 * 24 * 7, # weekly,
force-refresh on publish day instead`. The flat 7-day TTL just waits 7
days from whenever the last successful fetch happened — which drifts
out of alignment with the CFTC's real, fixed schedule over time (an
early fetch one week shifts every subsequent refresh earlier too, rather
than always landing on the actual publish day).

## The real schedule

The CFTC publishes COT data weekly, every **Friday at 3:30pm Eastern
Time**, reflecting the prior Tuesday's positioning. `agents/release_schedule.py`
answers, directly against this real schedule:

- `most_recent_cot_release_datetime(now)` — the most recent Friday
  3:30pm ET at or before `now`
- `next_cot_release_datetime(after)` — the next one after `after`
- `is_new_cot_release_available(last_fetched_at, now)` — has a real
  release happened since data was last actually fetched

Uses `zoneinfo` (standard library) for `America/New_York`, so EST/EDT
transitions are handled correctly automatically — verified directly for
both a winter (EST, UTC-5) and summer (EDT, UTC-4) date, rather than a
hardcoded offset that would silently drift wrong twice a year.

## Honest, accepted limitation

US federal holidays occasionally push the real CFTC release to the
following business day. This is not handled — doing so correctly would
require a maintained holiday calendar. A holiday-shifted week may show
slightly stale data as "not yet due for refresh" for one extra day.
Not silently pretended away — documented here directly.

## Dashboard integration

The Data Health page now shows the real most-recent and next-expected
release times directly, and — when the `COT_GOLD` dataset has been
fetched — flags with a clear warning if a new release has happened
since, rather than relying on the flat TTL alone to eventually catch up.

## Testing

10 tests in `tests/test_release_schedule.py`, including the exact
release-moment boundary, the EST/EDT distinction, naive-datetime
handling, and the cross-Friday-boundary release-detection case.
