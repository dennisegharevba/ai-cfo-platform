# Batch backtesting — running every signal against one asset at once

## Why this exists

`scripts/run_backtest.py` tests one signal at a time — after individually
testing several factors (Initial Jobless Claims, Housing Starts, GDP,
Seasonality) across separate sessions, running each of the platform's 21
available signals as 21 separate commands would mean 21 separate price
fetches and no way to compare results side by side without manually
tracking numbers across runs. `scripts/run_backtest_all.py` runs every
signal (or a chosen subset) against ONE asset in a single command,
fetching price history exactly once and printing one comparison table at
the end — the way a real quant researcher would actually want to screen
many candidate factors, sorted by which ones show the strongest
correlation.

## Usage

```
python scripts/run_backtest_all.py --asset SPY
python scripts/run_backtest_all.py --asset Gold --price-ticker GC=F
python scripts/run_backtest_all.py --asset SPY --signals "vix,GDP,Initial Jobless Claims"
```

`--signals` defaults to `all` (every signal in
`scripts.run_backtest.SIGNAL_FUNCTIONS`) or accepts a comma-separated
subset — useful for a faster first pass, given the honest scope caveat
below.

## What it reuses vs. what's genuinely new

Reuses everything already built and tested: `_resolve_price_ticker()`,
`_fetch_price_history()`, `_needs_fred_pacing()`, and
`agents.backtest_engine.run_backtest()` are all imported directly from
`scripts/run_backtest.py` and `agents/backtest_engine.py` — no
duplicated logic, no risk of the two scripts silently drifting apart on
how a signal gets scored or how significance gets computed.

Genuinely new: the price-history fetch happens exactly ONCE regardless
of how many signals are tested (verified directly with a test proving
`_fetch_price_history` is called exactly once even across two signals),
and the final summary table is sorted by `|correlation|` descending, so
the most promising results surface first rather than requiring a manual
scan through print output.

## Honest scope: this can genuinely take a long time

Testing all 16 Macro factors plus VIX/Real Yield/Treasury/Fed Policy
means up to 20 separate FRED point-in-time queries PER TEST DATE, each
individually paced (`--request-delay`, default 0.6s) to respect FRED's
rate limit — the same pacing mechanism built after a real rate-limiting
bug was found earlier in this project (see
`docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md`). A full multi-year run
at a reasonable step size is measured in tens of minutes, not seconds.
This is inherent to how FRED's vintage-query API works (one request per
series per date, no bulk endpoint) — not an inefficiency specific to
this script. Use `--signals` to restrict scope, or a wider `--step-days`,
for a faster first pass.

## Testing

5 tests in `tests/test_run_backtest_all.py`:
- An unknown signal name is reported clearly, not crashed on
- A missing `FRED_API_KEY` correctly blocks FRED-based signals
- **The core efficiency claim, proven directly**: price history is
  fetched exactly once regardless of how many signals are tested
- The summary table is genuinely sorted by `|correlation|` descending —
  proven with a deliberately weak signal and a deliberately strong one,
  confirming the strong one appears first
- A signal that returns zero usable data points doesn't crash the
  summary — shown honestly as `n/a`, not silently dropped or errored on

**620 tests total, all passing.**
