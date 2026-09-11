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

## Backtesting — has this actually been validated against real history?

Not until it's actually run with real data — but the machinery to do so
now exists, wired into this platform's existing signal-validation
infrastructure (`agents/backtest_engine.py`'s correlation validation and
`agents/strategy_backtest.py`'s simulated-trade metrics) rather than a
new, one-off validation approach. See `agents/swing_signal_backtest.py`
for the full reasoning; the short version:

- `connectors/cot_connector.py` gained `fetch_cot_history_range()` — a
  bulk historical fetch (the live `CotConnector` only ever fetches the
  most recent handful of weeks, deliberately; a backtest needs years).
- `agents/swing_signal_backtest.py`'s `swing_signal_history()` walks that
  full history sequentially and reuses `build_swing_signal()` UNMODIFIED
  at every week, recording a `(date, signed_confidence)` pair only on the
  weeks a signal actually fires — an event signal's silence isn't itself
  a reading. This output plugs directly into both existing backtest
  engines with no changes to either.
- `scripts/run_swing_signal_backtest.py` runs both and prints a full
  report: correlation with forward returns, and — if you'd traded every
  fired signal — win rate, profit factor, Sharpe/Sortino, max drawdown.

**Honest limitation, inherited and unavoidable**: every backtested signal
is COT-only. There is no historical news headline archive on this
platform (`agents/backtest_signals.py`'s own longstanding limitation), so
a backtested signal is always scored as `NewsAlignment.NO_DATA` — base
confidence, no news bonus or penalty. This answers a real but narrower
question than the live feature asks: does the COT-reversal-off-an-
extreme-reading mechanism alone have predictive value? If it doesn't,
the live feature's news cross-check can't be assumed to be what rescues
it, since news was never validated here either.

**Update, 2026-09-11 — actually run against real data.** Gold
(`GOLD - COMMODITY EXCHANGE INC.` / `GC=F`), 2021-09-12 to 2026-09-11,
8-week COT window (the live feature's default). The result is a real,
honest negative, not a "not yet validated" placeholder anymore:

- **56 signals fired** (55 usable for the correlation test — 1 skipped at
  the edge of the available price history).
- **Correlation vs. 20-day forward return: -0.221.** Negative direction —
  bullish readings tended to precede *worse* forward returns — but below
  this platform's own significance threshold (0.267) at n=55, so on its
  own this number is not conclusive either way.
- **Strategy backtest** (one unit per fired signal, fixed holding period,
  no position sizing, no slippage beyond the engine's flat built-in cost):
  55 trades, 21W/34L, **38.2% win rate, profit factor 0.46**, total
  compounded return **-45.1%**, Sharpe **-1.00**, Sortino **-0.87**, max
  drawdown **-49.1%**.

Profit factor 0.46 means roughly $2.17 lost for every $1 won — this is not
a "no edge detected" result, it's a losing one, and both the correlation
and strategy numbers point the same direction, which is more meaningful
than the correlation test's significance flag alone. Worth weighing before
drawing a firm conclusion: almost every fired signal scored the bare
`confidence=50.0` (the `NEWS_CONFIRMS_BONUS`/`NEWS_CONTRADICTS_PENALTY`
never apply here, per the NO_DATA limitation above), and
`EXTREME_PERCENTILE_BONUS` only applied on 6 of the 55 signals — so what
was actually tested is the raw "COT reversal off a trend" mechanism in
isolation, not the full live confidence model with real news scoring
folded in. This is also one asset over one five-year window; it does not
by itself say whether this is Gold-specific or a systemic problem with the
mechanism across the watchlist. Run
`scripts/run_swing_signal_backtest.py --asset <name>` (any commodity/FX
display name from `config/watchlist.py`, e.g. `Silver`, `"EUR/USD"`,
`"WTI Crude Oil"`) to extend this to other assets before trusting or
distrusting the feature as a whole — that comparison is in progress.
