# Swing Signal

## What this adds

Every existing department in this platform — `positioning_agent_base.py`,
`ChiefExecutionOfficer`, `ChiefTradeDecisionOfficer` — is built for a
**position trader**: someone assembling a multi-week thesis, where CFTC
Non-Commercial (large speculator) positioning turning against that
thesis is a *risk* to discount (see `MOMENTUM_REVERSAL_PENALTY = -15.0`
in `positioning_agent_base.py`).

A **swing trader** wants the opposite framing of the exact same data:
the moment positioning starts reversing against an established trend is
not a risk to a standing thesis — it *is* the setup. `agents/swing_signal.py`
builds this as a fully separate, additive pipeline that reuses the
platform's existing COT reversal detection and news sentiment scoring
without duplicating or modifying either.

## Why a separate pipeline, not a flag on the existing one

`positioning_agent_base.py` is tuned for confidence in a *standing*
thesis: `BASE_CONFIDENCE = 55.0`, a real penalty for a reversal, and a
further penalty for an extreme percentile reading (crowded positioning
threatens the thesis holding). A swing setup inverts every one of those:
a reversal is required (not penalized), and an *extreme* percentile
reading is a bonus, not a penalty — a reversal off a crowded reading is
a textbook mean-reversion setup, not a warning sign.

Rather than threading a `mode` flag through the existing confidence math
(and risking a mistake there regressing the position-trading pipeline
that this platform's production cycle already depends on), `agents/swing_signal.py`
is a new, independent module. It imports and reuses:

- `agents.speculative_positioning_analysis.classify_momentum_signal()` —
  the exact same "continuation" / "reversal_watch" / "stable" /
  "insufficient_data" classification the position-trading agents already
  use, unmodified.
- `agents.positioning_scoring.net_position_trend_score()` and
  `agents.speculative_positioning_analysis.latest_weekly_change()` — the
  same multi-week trend score and week-over-week change.
- `agents.sentiment_scoring.news_sentiment_score()` (via whatever score
  the caller passes in) — the same broad market news scoring
  `ChiefSentimentOfficer` already produces.
- `agents.release_schedule.is_new_cot_release_available()` — reused for
  Telegram alert deduplication (see below), not just COT staleness.

`build_swing_signal()` returns `None` for anything that is not a genuine
`"reversal_watch"` — a continuation, a stable read, or insufficient
history all produce no signal at all, deliberately, since those are not
swing setups.

## Confidence model

```
BASE_CONFIDENCE = 50.0
NEWS_CONFIRMS_BONUS = +20.0       # broad market news agrees with the new direction
NEWS_CONTRADICTS_PENALTY = -20.0  # broad market news disagrees
EXTREME_PERCENTILE_BONUS = +10.0  # opposite sign from positioning_agent_base.py's penalty
NEWS_NEUTRAL_BAND = 10.0          # |score| <= 10 counts as neutral, not a lean either way
```

Confidence is clamped to `[0, 100]`.

## Honest, accepted limitation

The platform has exactly one broad-market news source (`config.settings.NEWS_RSS_URL`),
not a per-commodity or per-currency feed. `build_swing_signal()`'s news
check is therefore always a **broad market** sentiment read, applied the
same way regardless of which specific asset the COT reversal is on. This
is disclosed directly on the dashboard page rather than presented as a
per-asset news check it isn't. A `NewsAlignment.NO_DATA` signal (no
sentiment score available at all, e.g. the RSS source is unreachable)
still fires with `BASE_CONFIDENCE` and no bonus/penalty — a positioning
reversal alone is still worth surfacing to a swing trader even with no
news cross-check available that scan.

## Delivery: dashboard + Telegram

- **`dashboard/pages/8_Swing_Signals.py`** — a "Run live scan now" button
  that walks the platform's entire configured FX/commodity watchlist
  (`config.watchlist.WATCHLIST_DAILY`), fetching one shared broad-market
  sentiment read plus each market's own COT history, and a "Recent
  signals" section (persisted, filterable by lookback window) with a
  per-signal manual "Send Telegram alert" button.
- **`scripts/run_daily_cycle.py`** — the same detection runs
  automatically as part of the existing scheduled daily cycle
  (`.github/workflows/scheduled_run.yml`), reusing the COT/sentiment data
  the cycle already fetches for its normal departments rather than
  fetching it twice, and sends a Telegram alert automatically via the
  existing `telegram.telegram_alerter.TelegramAlerter` when credentials
  are configured.

Both paths are additive: `run_cycle()`'s existing public signature and
return value are unchanged, so nothing about the position-trading
pipeline's own behavior or tests were touched to add this.

## Alert deduplication

The underlying CFTC COT data only changes once a week (see
`docs/ARCHITECTURE_COT_RELEASE_SCHEDULE.md`), but the daily cycle runs
Monday–Friday. Without deduplication, the same reversal would trigger a
fresh Telegram alert on every single weekday it remains detected.
`should_send_swing_alert()` reuses `agents.release_schedule.is_new_cot_release_available()`
against the last time this asset+direction was actually alerted
(`database.report_store.ReportStore.get_latest_alerted_swing_signal()`)
— so a swing signal is alerted once per real COT release, not once per
cycle run.

## Persistence

`swing_signals` table (`database/schema.py`), added via the existing
`_migrate()` pattern so it appears cleanly in both fresh and pre-existing
database files. `alert_sent` tracks whether a Telegram alert has gone out
for that specific saved row, independent of the dashboard's manual send
button vs. the daily cycle's automatic send — either path calls the same
`ReportStore.mark_swing_signal_alerted()`.

## Testing

16 tests in `tests/test_swing_signal.py` (reversal detection in both
directions, non-reversal cases correctly returning `None`, news
alignment in all four states, confidence ordering and clamping,
`headline()` content, alert-dedup edge cases), 7 new tests in
`tests/test_report_store.py` for `swing_signals` persistence, 4 new
integration tests in `tests/test_run_daily_cycle.py` covering the full
detect-and-persist and Telegram-alert-on-reversal paths end to end
through the real daily cycle, and 3 new tests in
`tests/test_dashboard_pages.py` (executed via Streamlit's `AppTest`
harness, not just imported) covering the empty state, an offline live
scan, and rendering a real saved signal.
