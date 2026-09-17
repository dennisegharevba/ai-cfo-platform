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

**Update, 2026-09-11 — actually run against real data, across three
assets.** Same window (2021-09-12 to 2026-09-11) and 8-week COT window
(the live feature's default) for all three. The result is a real,
consistent negative, not a "not yet validated" placeholder anymore, and
not asset-specific either:

| Asset | Signals | Correlation vs. 20d fwd return | Trades (W/L) | Win rate | Profit factor | Total return | Sharpe | Max DD |
|---|---|---|---|---|---|---|---|---|
| Gold (`GC=F`) | 56 | -0.221 (n=55, not significant) | 55 (21/34) | 38.2% | 0.46 | -45.1% | -1.00 | -49.1% |
| EUR/USD (`EURUSD=X`) | 82 | -0.146 (n=80, not significant) | 80 (36/44) | 45.0% | 0.58 | -26.2% | -0.76 | -30.7% |
| WTI Crude Oil (`CL=F`) | 66 | -0.111 (n=66, not significant) | 66 (28/38) | 42.4% | 0.74 | -61.9% | -0.39 | -67.9% |

No single one of these correlations clears this platform's own
significance threshold on its own. But the pattern across three assets
from three different, largely uncorrelated markets (a metal, a currency
pair, an energy future) is what makes this more than noise: **all three
correlations are negative** (bullish readings preceded worse forward
returns in every case, not just Gold's), and **all three strategy
backtests are net losers** (profit factor under 1.0 in every case — Gold
0.46, EUR/USD 0.58, WTI 0.74 — with double-digit-to-50%+ compounded losses
and drawdowns in every case). Three independent losing results in the same
direction is meaningfully stronger evidence than any one of them alone,
even though each individually falls short of the significance bar. This
reads as a systemic issue with the underlying mechanism, not a Gold
quirk.

Worth weighing before drawing a final conclusion: almost every fired
signal across all three assets scored the bare `confidence=50.0` (the
`NEWS_CONFIRMS_BONUS`/`NEWS_CONTRADICTS_PENALTY` never apply here, per the
NO_DATA limitation above; `EXTREME_PERCENTILE_BONUS` applied only rarely)
— so what was actually tested is the raw "COT reversal off a trend"
mechanism in isolation, not the full live confidence model with real news
scoring folded in. A consistently *negative* correlation in every asset
also raises a specific, testable hypothesis rather than just "no edge":
that a single-week pullback in COT positioning off an extreme reading may
more often be a pause within the original trend (which then resumes) than
a genuine reversal — i.e. the signal's direction may be backwards more
often than not, not merely uninformative. That is a hypothesis, not a
conclusion — it would need its own backtest (scoring the *fade* of each
fired signal against the same forward returns) before acting on it. Not
yet run.

**Given three-for-three losing results across unrelated asset classes,
this feature's live Telegram alerts should not be trusted as trading
signals until this is resolved** — either by the fade hypothesis above, by
a reworked confidence model, or by further evidence that a longer/shorter
holding period or added filters change this outcome. This doc will be
updated once that follow-up work happens.

## Update, 2026-09-11 — alerts gated off, and the fade hypothesis is now testable

Two follow-ups landed the same day as the three-asset result above, both
additive (nothing about signal detection, scoring, or the confidence model
changed):

**`config.settings.SWING_SIGNAL_ALERTS_ENABLED`** (default `false`) now
gates the actual Telegram *send* in both alert paths — `scripts/run_daily_cycle.py`'s
automatic path and `dashboard/pages/8_Swing_Signals.py`'s manual "Send
Telegram alert" button. Detection and persistence are untouched by this
flag: signals still fire, still save to `swing_signals`, and still show up
on the dashboard either way, so real data keeps accumulating; only whether
a message actually reaches Telegram is controlled by the flag. The
dashboard page now also shows an explicit warning banner (with this
section's numbers) whenever the flag is off, and the daily cycle logs
"would have fired but suppressed" instead of silently dropping it. This
directly operationalizes the "should not be trusted... until this is
resolved" line above, rather than leaving it as a comment nobody enforces.
Flip it to `true` (env var) once one of the resolutions below actually
lands.

**`scripts/run_swing_signal_backtest.py --fade`** tests the fade
hypothesis raised above: it takes the exact same `swing_signal_history()`
output and negates each fired signal's confidence (`BULLISH_TURN` <->
`BEARISH_TURN`) before handing it to the same two backtest engines,
unmodified. Nothing about `build_swing_signal()` or how a signal is
detected changes — only the sign of the already-computed score at the
call site in the script.

**One thing `--fade` does NOT tell you on its own**: the correlation
number's sign flips with identical magnitude under negation by
construction (Spearman correlation of `-x` vs `y` is exactly `-`
correlation of `x` vs `y`), so a faded run "clearing the significance
threshold" happens only if the ORIGINAL run's magnitude already cleared
it — which none of the three original runs did (Gold -0.221 vs. threshold
0.267, EUR/USD -0.146 vs 0.221, WTI -0.111 vs 0.242). The correlation
column is not the deciding evidence either way here; the strategy backtest
(profit factor, total return, Sharpe) is, because trade-level costs and
compounding are NOT a simple sign flip of the original.

## Update, 2026-09-11 — fade hypothesis actually run: confirmed, 3-for-3

Run same-day against the same three assets, same window (2021-09-12 to
2026-09-11), same 8-week COT window:

| Asset | Signals | Corr (unchanged magnitude) | Trades (W/L) | Win rate | Profit factor | Total return | Sharpe | Max DD |
|---|---|---|---|---|---|---|---|---|
| Gold | 55 | +0.221 (n=55, not significant) | 55 (33/22) | 60.0% | **2.01** | **+59.8%** | 0.90 | -8.1% |
| EUR/USD | 80 | +0.146 (n=80, not significant) | 80 (43/37) | 53.8% | **1.48** | **+22.1%** | 0.55 | -10.8% |
| WTI Crude Oil | 66 | +0.111 (n=66, not significant) | 66 (38/28) | 57.6% | **1.31** | **+34.0%** | 0.35 | **-59.7%** |

The correlation column moved exactly as predicted above (same magnitude,
flipped sign, still individually short of each asset's significance
threshold — that part carries no new information). The strategy column is
what matters, and it is NOT a mirror image of the original run: every
asset flipped from a losing strategy to a winning one (profit factor from
0.46/0.58/0.74 to 2.01/1.48/1.31), win rate crossed 50% in all three, and
Sharpe went from negative to positive in all three. This is the same
three-for-three pattern as the original negative result, just inverted —
real, consistent evidence for the fade hypothesis specifically (not merely
"the original doesn't work," which was already known).

**Two things this result does NOT yet establish, before touching
`SWING_SIGNAL_ALERTS_ENABLED` or the live signal's direction:**

1. **WTI's -59.7% max drawdown.** A profit factor of 1.31 and a positive
   Sharpe coexist here with a drawdown that would have wiped out most of
   an account's equity at some point in this window. Profit factor and
   Sharpe describe average behavior; they do not rule out a strategy being
   practically unrideable. This alone blocks "just flip it live" for WTI
   regardless of the other numbers.
2. **This may not be a new, independent signal at all.** Fading
   `reversal_watch` — betting the established multi-week trend reasserts
   rather than betting on the turn — is conceptually the same bet
   `agents/positioning_agent_base.py`'s trend score already makes. Both
   sections below settle this: the wider run shows the 3-asset pattern
   didn't generalize, and the redundancy suspicion turned out to be
   exactly, provably correct.

## Update, 2026-09-11 — widened to the full watchlist: the 3-for-3 pattern did NOT generalize

`scripts/run_swing_signal_backtest_all.py` (new) runs both the original
and the fade across every FX/commodity market in `WATCHLIST_DAILY` in one
command, sharing one COT fetch + one price fetch per market between them
(mirroring `scripts/run_backtest_all.py`'s batching pattern):

```
python scripts/run_swing_signal_backtest_all.py
```

Run same-day against all 30 markets (21 usable — 9 commodities have no
Yahoo ticker mapped yet: Soybean Oil, Soybean Meal, Cotton, Coffee, Cocoa,
Sugar, Live Cattle, Lean Hogs, Feeder Cattle):

**13 of 21 markets show a losing original signal; 8 of 21 show a winning
one.** That is a real tilt toward the fade direction, but nowhere near the
clean 3-for-3 the hand-picked Gold/EUR/USD/WTI sample suggested — and the
8 "original wins" are not small-sample noise. Five of them have large,
meaningful sample sizes and strong results IN THE ORIGINAL DIRECTION:

| Asset | N | Original PF | Original return | Faded PF | Faded return |
|---|---|---|---|---|---|
| USD/MXN | 81 | **2.34** | **+74.4%** | 0.38 | -49.5% |
| Corn | 78 | **1.49** | **+70.2%** | 0.64 | -58.2% |
| Wheat | 83 | **1.45** | **+78.5%** | 0.66 | -67.1% |
| USD/BRL | 90 | **1.33** | **+23.4%** | 0.67 | -29.9% |
| DXY | 71 | **1.28** | **+10.6%** | 0.67 | -17.1% |

USD/MXN in particular is a warning, not just a counterexample: it was the
single best original-direction result in the whole watchlist, and blindly
fading it (as a universal rule would have) costs -49.5% with a -51.0% max
drawdown. **A blanket "always fade" rule would have been actively harmful
on real, well-sampled markets, not merely unproven.**

A second pattern: every market's original and faded profit factor are
near-perfect mirror images of each other (PF > 1 on one side lines up with
PF < 1 on the other, essentially without exception). That is consistent
with each market simply having had ONE dominant multi-year trend over
2021–2026 (gold's bull run, the peso's multi-year move, the grains
supercycle) — whichever side of that trend a market's fired signals
happened to fall on determined whether it looked like a "winner," which is
a regime effect over this specific 5-year window, not necessarily
skill from the COT-reversal mechanism in either direction. Several results
are additionally on samples too thin to mean anything regardless of
direction: GBP/USD (5 trades), NZD/USD (5), Natural Gas (4), USD/ZAR (8),
Copper (9).

**Conclusion: neither "trade the signal as designed" nor "blanket-fade
it" is supported.** `SWING_SIGNAL_ALERTS_ENABLED` stays `false`. Flipping
the live signal's default direction is off the table, not just paused —
USD/MXN alone demonstrates it would be harmful on a real, large-sample
market, not merely unvalidated.

## Update, 2026-09-11 — the redundancy suspicion is proven, not just plausible

The suspicion above (fading may just be rediscovering
`positioning_agent_base.py`'s existing trend read) is exactly correct, and
provably so — not a matter of interpretation:

- `agents/positioning_agent_base.py` line 182: `bias_score = spec_trend`
  where `spec_trend = net_position_trend_score(...)`. The Chief
  Commodity/FX Analyst's existing directional call, for every market,
  every day, IS the sign of `net_position_trend_score` — nothing more.
- `agents/speculative_positioning_analysis.classify_momentum_signal()`
  only returns `"reversal_watch"` (the ONLY case `build_swing_signal()`
  ever fires on) when `(trend_score >= 0) != (weekly_change >= 0)` — i.e.
  a reversal is, BY DEFINITION, exactly the case where this week's move
  disagrees with `trend_score`'s sign.
- `agents/swing_signal.py`'s direction is the sign of `weekly_change`.
  Since a fired signal's `weekly_change` always has the OPPOSITE sign of
  `trend_score` (that's what makes it a reversal), fading it (negating the
  direction) always lands on the SAME sign as `trend_score`.

Chained together: **fading a fired Swing Signal is mathematically
identical, in every case, to betting the sign of `net_position_trend_score`
— which is exactly `positioning_agent_base.py`'s existing `bias_score` for
that same asset, that same day.** Verified directly against the real code
(not asserted from reading it): 20,000 randomized synthetic COT histories
fed through the actual `build_swing_signal()` and
`net_position_trend_score()` produced 7,111 fired signals, and the faded
direction matched `trend_score`'s sign in **7,111 of 7,111** — zero
exceptions.

**What this means in practice**: a "faded Swing Signal" alert carries zero
directional information beyond what the Chief Commodity/FX Analyst's
`bias_score` already shows for that market on the dashboard. There is no
second, independent edge to enable here — flipping the feature's direction
would just be re-surfacing the existing trend read through a second UI
element with a different name, dressed up as a new discovery. If there's
still a case for keeping a "reversal_watch" alert at all, it would have to
be argued as a NOTIFICATION-TIMING feature ("your existing trend thesis on
this asset is being tested right now, and it's on track to reassert") —
never as a new source of alpha, since the direction it would fire on
provides no information the platform doesn't already display.

This is why `tests/test_swing_signal.py` now includes
`test_faded_direction_matches_trend_score_sign` — a permanent regression
check that this specific relationship is understood and intentional,
should either `build_swing_signal()` or `net_position_trend_score()` ever
change.
