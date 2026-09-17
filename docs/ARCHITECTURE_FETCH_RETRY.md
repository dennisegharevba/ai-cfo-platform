# Retry logic for intermittent Yahoo Finance failures

## What this fixes

Repeated real screener runs surfaced a consistent pattern: large,
genuinely-listed companies — Meta, Starbucks, Synopsys — failing with
`"possibly delisted; no price data found"`. None of them are actually
delisted. `yfinance` isn't an official Yahoo API; it queries Yahoo's own
internal endpoints without a real support agreement, and when Yahoo
rate-limits or briefly hiccups, `yfinance`'s own error handling reports
that as "possibly delisted" — a misleading message for what's really
just "no data came back this time."

**The failures are genuinely intermittent, not predictable.** One real
run failed on `BTC-USD` at position 22 of 122 — early in the scan.
Slowing every request down (`--request-delay 1.0`) did not reliably
reduce failures on a follow-up run; the set of tickers that failed
changed almost entirely between runs. Only `JNPR` and `IPG` failed
consistently across multiple runs — everything else looked essentially
random from one run to the next.

## The fix

`scripts/run_backtest.py`'s `_fetch_price_history()` — the single shared
function used by `run_backtest.py`, `run_backtest_all.py`,
`run_screener.py`, and `run_full_pipeline.py` — now retries up to 2
times (configurable via `max_retries`), 2 seconds apart (`retry_delay`),
before giving up on a ticker. Fixing it here means every script that
calls it benefits automatically, not just the screener.

A ticker that still fails after exhausting retries still raises the
real `DataSourceError`, with the real message — callers that print
`"fetch failed — {exc}"` still report honestly which ticker failed and
why, never silently swallowed into an empty result.

## Verified directly

- A transient failure that succeeds on retry returns real data, proven
  directly against a mock that fails once then succeeds
- A ticker that never recovers still raises the real, original error
  message — not swallowed
- Exactly `max_retries + 1` total attempts, proven by counting calls,
  not just checking the final outcome
- The common case (no failure at all) never sleeps — proven by
  asserting `time.sleep` is never called when the first attempt
  succeeds, so this adds zero overhead to the vast majority of requests
- A realistic reconstruction of the exact live finding — a ticker
  failing with "possibly delisted" on the first attempt, succeeding on
  the second — recovers correctly

## Testing

5 new tests in `tests/test_run_backtest.py`. **755 tests total, all
passing.**

## Honest scope

This recovers *transient* failures — a request that fails once and
would have succeeded moments later. It does not, and cannot, recover a
ticker that's genuinely unavailable (a real rate-limit lockout lasting
longer than the retry window, or a ticker that's actually wrong). Some
fetch failures will still happen; they should now be rarer, not
eliminated entirely.
