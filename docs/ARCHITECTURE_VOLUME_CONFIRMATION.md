# Volume confirmation scoring

## What this adds

Before this, every technical score on the platform was pure price
action — SMA crossovers, RSI, MACD. Volume was fetched nowhere and used
nowhere, a real, acknowledged gap: a price move on heavy volume means
something different from the same move on thin volume, a well-established
idea in classical technical analysis going back to Dow Theory (volume
should confirm a genuine trend; a move without volume backing it is
treated as less reliable).

## What was deliberately NOT built

BOS (Break of Structure) and CHOCH (Change of Character), from Smart
Money Concepts / ICT, were considered and set aside. That framework is
popular in retail trading circles but sits on much weaker footing than
volume confirmation: marking a "swing high" or "structure break" is
inherently somewhat subjective, which makes it prone to looking clean in
hindsight and considerably harder to encode as a consistent,
non-overfit rule. Volume confirmation and cross-asset volatility
normalization (the earlier fix in this same file's history) are both
well-established, low-controversy ideas; BOS/CHOCH is not in the same
category of rigor. If it's ever built, it should be built as an explicit
experiment, backtested against the existing signals via
`scripts/run_strategy_backtest.py`, not trusted on reputation alone.

## The fix, in three pieces

**1. `connectors/yahoo_history_connector.py`** now includes `volume` in
every fetched row — additive, backward-compatible with any existing
consumer that only reads `close`/`high`/`low`. Defaults to `0.0` (never
fabricated from close price) when Yahoo doesn't report usable volume for
an instrument — true for some FX pairs and a few commodities.

**2. `agents/technical_indicators.py`** adds two new, additive functions:
- `volume_confirmation_ratio()` — recent average volume vs. a 50-day
  baseline. Above 1.0 means elevated (real backing); below 1.0 means
  the move lacks confirmation. Returns `None` (never a fabricated ratio)
  when there isn't enough history or the whole baseline is unusable
  (all-zero, Yahoo's own honest "no data" signal).
- `volume_confirmation_multiplier()` — converts that ratio into a
  bounded `[0.85, 1.15]` conviction adjustment. **Missing volume data
  maps to an exactly neutral 1.0 — never a penalty.** This is
  deliberate: scoring an asset worse simply because Yahoo doesn't cover
  its volume would repeat, via a new mechanism, the exact
  cross-asset-class fairness mistake already found and fixed for
  `trend_score()` earlier in this project.

**3. `agents/opportunity_screener.py`'s `screen_asset()`** takes an
optional `volumes_oldest_first` parameter (defaults to `None`, fully
backward compatible with every existing caller and test) and applies the
multiplier to `conviction_score` when volume data is provided.

## Efficiency: fetched once, not twice

`scripts/run_screener.py` now calls `_fetch_price_and_volume_history()`
— a new function added alongside the existing `_fetch_price_history()`
(unchanged, still used by every other script) — and derives both the
close-only view and the volume list from that single fetch, rather than
doubling network requests per asset. Doubling requests would have
worsened the exact intermittent-failure problem the retry logic was
built to address (see `docs/ARCHITECTURE_FETCH_RETRY.md`); both
functions share the same retrying fetch internally
(`_fetch_raw_history_rows()`), so the retry logic lives in one place,
not duplicated.

## Verified end-to-end

A full CLI-level test gave three assets (MSFT, IBM, EUR/USD) the exact
same underlying trend strength, differing only in recent volume: MSFT
(elevated recent volume) correctly scored ABOVE its raw bias-implied
conviction, IBM (below-average recent volume) correctly scored BELOW
it, and EUR/USD (no usable Yahoo volume, the common real case for FX)
scored exactly proportional to its bias with a neutral multiplier — no
penalty for lacking data Yahoo doesn't provide.

## Testing

15 new tests: 4 in `tests/test_yahoo_history_connector.py` (real
volume, missing column, NaN handling), 12 in
`tests/test_technical_indicators.py` (ratio and multiplier, including
the core fairness test), 4 in `tests/test_opportunity_screener.py`
(boost, reduction, and the no-penalty-for-missing-data fairness test at
the full `screen_asset()` level), plus 4 in `tests/test_run_backtest.py`
for the new volume-aware fetch function sharing the same retry logic.
**776 tests total, all passing.**
