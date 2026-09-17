# Backtesting: signal validation, not P&L simulation

## What this answers, and what it doesn't

Per an explicit scoping decision: this platform never places trades or
sizes positions, so "backtesting" here means SIGNAL VALIDATION — did more
bullish historical readings actually precede better subsequent price
performance than more bearish ones? This is the same "information
coefficient" concept quant researchers use to validate a factor before
ever trading on it. It does NOT simulate hypothetical trades, P&L, win
rates, or drawdowns from following the signal — that's a fundamentally
different (and much larger) undertaking this platform doesn't attempt.

## The hardest problem: point-in-time correctness

Every one of this platform's live connectors (FRED, CFTC, SEC, Yahoo)
fetches the CURRENT, most up-to-date data. A historically honest backtest
needs to know what was known AT EACH HISTORICAL MOMENT — not today's
revised numbers. Using today's revised 2023 CPI figure to test what
Chief Macro Officer would have said in 2023 is a classic look-ahead-bias
mistake: the signal would appear smarter than it could actually have
been, because it's being fed information that didn't exist yet.

This matters differently for different data:
- **Survey-based economic statistics** (CPI, GDP, Retail Sales, NFP,
  JOLTS, Average Hourly Earnings, Federal Debt) genuinely get revised
  after initial publication.
- **Daily market-observed series** (Fed Funds Rate, 10Y Treasury/TIPS
  yields, VIX) are prices, not survey statistics — they are NOT
  meaningfully revised. `connectors/fred_historical.py`'s
  `NON_REVISED_SERIES` documents exactly which ones.
- **CFTC COT reports** are weekly snapshots, inherently point-in-time
  correct by nature — no revision concept applies.
- **A calendar month** (Seasonality's only input) is always known,
  never revised, by definition.

## `connectors/fred_historical.py` — the piece that makes this honest

FRED's own API (the same one powering the public ALFRED vintage archive)
accepts `realtime_start`/`realtime_end` parameters. Querying with both
set to a single historical date returns the value of a series EXACTLY AS
IT WAS PUBLISHED/KNOWN on that date — not today's revision.
`fetch_point_in_time_value(series_id, api_key, as_of_date)` uses this
directly. It never raises — a missing series, a network failure, a bad
response all return `None`, so a backtest loop can simply skip that data
point rather than crash or fabricate a value, the same convention every
live connector in this platform already follows.

**Honest limitation**: there's no bulk vintage-query endpoint — this is
one API call per (series, date) pair. A broad historical backtest across
many dates genuinely takes real time to run; this is inherent to how
FRED's vintage data works, not an inefficiency in this implementation.

## `agents/backtest_engine.py` — the reusable, signal-agnostic core

Deliberately knows nothing about any specific signal — it takes a list of
`(date, bias_score)` pairs someone else computed, and a price series, and
tells you how well they lined up. Every signal plugs into this SAME
engine rather than reinventing its own correlation math.

- **Spearman rank correlation**, not Pearson — robust to outliers and to
  non-linear-but-monotonic relationships, the standard choice for this
  kind of validation. Computed via a from-scratch rank transform plus the
  ALREADY-EXISTING `agents.risk_calculations.pearson_correlation`
  (Spearman IS Pearson-on-ranks) — no new statistics dependency.
- **No scipy** — deliberately, to match this platform's established
  "pure Python, no heavy new dependencies" convention
  (`agents/risk_calculations.py` already hand-rolls VaR/drawdown/
  correlation the same way, even though scipy happened to be available in
  this development sandbox).
- **Statistical significance** uses a standard large-sample normal
  approximation (`|r| > z/√(n-1)`) rather than a from-scratch
  t-distribution CDF — honestly labeled in the code as an approximation,
  most accurate for n ≥ ~30, since a hand-rolled CDF implementation could
  easily be subtly wrong in a way that's worse than not having one.
- **Never fabricates a data point**: any signal date whose forward return
  can't be found in the price history is excluded and counted in
  `skipped_dates`, never interpolated or estimated.

## `agents/backtest_signals.py` — twenty-one real signals wired in

| Signal | Point-in-time risk | Reuses |
|---|---|---|
| Seasonality | None — a calendar month is always known | `agents.seasonality_scoring.score_seasonality` |
| VIX | None — daily market price | `agents.institutional_market_regime.score_vix` |
| 10Y TIPS Real Yield | None — daily market price | `agents.institutional_market_regime.score_real_yield` |
| 10Y Treasury Yield | None — daily market price | `agents.institutional_market_regime.score_treasury_yield` |
| Fed Funds Rate trend | None — daily market rate | `agents.institutional_market_regime.score_fed_policy` + `agents.trend_scoring.percent_change_score` |
| **All 16 Chief Macro Officer factors** (CPI, Core CPI, PPI, Core PCE, GDP, Retail Sales, Unemployment Rate, NFP, Average Hourly Earnings, JOLTS, Initial Jobless Claims, Dollar Index, Credit Spreads, Consumer Confidence, Housing Starts, Federal Debt) | Solved properly via `connectors.fred_historical.fetch_point_in_time_history()` | `agents.trend_scoring.series_trend_score` — the SAME function the live agent calls |

### `macro_factor_signal()` — the piece that closes the previously-deferred gap

This was explicitly deferred in the first version of this document
("genuinely harder... a real, bounded follow-up, not attempted here").
Built now specifically so the normalization thresholds recalibrated in
`docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md` can eventually be
validated against real historical data, not just reasoned defensibly.

Two things needed solving:

1. **A full vintage-correct history window, not just a single point-in-time
   value.** The live agent computes its trend from a 5-observation window
   (oldest vs. newest), so a historically honest backtest needs that SAME
   window, as it was known on a given historical date.
   `connectors/fred_historical.py` gained `fetch_point_in_time_history()`
   — returns the same `history` shape `FredConnector`'s live payload
   uses, but built from FRED's vintage-query parameters.
2. **Zero duplicated calibration values.** `macro_factor_signal(factor_name, ...)`
   looks up that factor's exact `(key, lower_is_bullish, normalization_pct)`
   directly from `agents.chief_macro_officer._FACTOR_SPECS` — never a
   second copy of those numbers that could silently drift out of sync
   with the live agent. `test_macro_factor_signal_uses_that_factors_own_calibrated_normalization`
   proves this directly: the same synthetic 8% move clamps for CPI
   (still 5.0) but not for Initial Jobless Claims (now 15.0) — read from
   the live spec, not hardcoded in the test.

`MACRO_FACTOR_NAMES` (built from `_FACTOR_SPECS`, so it can never list a
factor that doesn't actually exist) gives all 16 valid `--signal` values
for `scripts/run_backtest.py` — e.g.
`--signal "Initial Jobless Claims" --asset SPY`.

## Real bugs and mistakes caught along the way — not glossed over

- **Two floating-point test failures**: an early test asserted
  `spearman_correlation(...) == 1.0` for a perfect monotonic relationship
  — the actual computed value was `0.9999999999999998`, correct given
  floating-point arithmetic, but the exact-equality assertion was wrong.
  Fixed with a tolerance comparison.
- **A synthetic price series that went negative**: an early test
  constructed prices as `200.0 - i * 0.5` over 700 days — this crosses
  zero and goes negative partway through, making the "% return" math
  produce nonsensical swings (±200%, +100%) that had nothing to do with
  the intended relationship. The engine's math was correct; the test data
  was economically nonsensical. Fixed by explicitly constructing price
  anchor points per signal date with a guaranteed-positive, directly
  controlled relationship, rather than deriving behavior indirectly from
  a single global formula.
- **Two mis-judged threshold assertions**: two signal-wrapper tests
  asserted the wrong expected score because the test author (not the
  code) miscalculated which scoring band a given basis-point change would
  land in. Fixed by checking the actual threshold constants rather than
  assuming.
- **A real usability bug in `scripts/run_backtest.py`**, caught by
  actually running it live: for the Seasonality signal, the SIGNAL needs
  a display name ("Gold") but PRICE HISTORY needs a Yahoo ticker
  ("GC=F") — two different things that had been conflated into one
  `--asset` argument. Fixed with auto-resolution via the existing
  `config/watchlist.py` ticker mappings, plus an explicit
  `--price-ticker` override for anything not covered.

## `scripts/run_backtest.py` — what you'll actually run

```
python scripts/run_backtest.py --signal seasonality --asset Gold
python scripts/run_backtest.py --signal vix --asset SPY
python scripts/run_backtest.py --signal real_yield --asset GC=F
python scripts/run_backtest.py --signal treasury_yield --asset SPY
python scripts/run_backtest.py --signal fed_policy --asset SPY
```

Needs real network access (and a real `FRED_API_KEY` for anything but
Seasonality) — this cannot produce a real answer from this development
sandbox, verified directly: the Seasonality signal computation itself
works with zero network access, but the price-history fetch correctly
fails with a clear, honest error rather than crashing or fabricating
results.

## Testing

- 11 tests for `connectors/fred_historical.py` (mocked HTTP, matching this
  project's established connector-testing pattern), including direct
  proof the vintage-query parameters are genuinely sent, and (for the new
  history function) that it returns the same shape the live
  `FredConnector` payload uses
- 13 tests for `agents/backtest_engine.py`
- 16 tests for `agents/backtest_signals.py`, including direct proof that
  `macro_factor_signal()` reads each factor's normalization threshold
  from the live `_FACTOR_SPECS` rather than a duplicated value
- 580 tests total, all passing
- `scripts/run_backtest.py` verified live against this sandbox: the
  ticker auto-resolution and the FRED-key guard both confirmed working
  correctly; the actual data fetch correctly and honestly fails given
  this environment's lack of network access

## What's deliberately still deferred

- **COT-based Commodity/FX Analyst** — would need extending
  `connectors/cot_connector.py` to fetch a wide historical date range
  (CFTC's API supports this; unbuilt).
- **News Sentiment** — genuinely impossible with this platform's
  RSS-based connector, which has no historical headline archive.
  Permanently excluded, not deferred.
- **P&L/trade simulation** — deliberately out of scope per the original
  framing decision (see the top of this document).

(Macro's survey-revised factors were previously listed here as deferred —
now built, see the `macro_factor_signal()` section above.)
