# A real bug: `scripts/run_backtest.py` silently dropped every price row

## How this was found

Not from testing — from the user actually running a real backtest with a
working `FRED_API_KEY`:

```
python scripts/run_backtest.py --signal "Initial Jobless Claims" --asset SPY
```

The FRED side worked perfectly — all 61 of 61 historical dates returned a
usable signal reading, confirming the point-in-time vintage-query
machinery genuinely works end to end. But the price side silently failed:

```
Fetching price history for SPY...
  Got 0 daily closes.
...
Sample size:         0 (skipped 61)
Correlation:         None
```

No error message, no crash — just zero usable price data, silently.

## Root cause

`connectors/yahoo_history_connector.py` builds each history row's `"date"`
field from a pandas `Timestamp`'s `.isoformat()`:

```python
"date": idx.isoformat(),
```

That produces a string WITH a time component —
`"2026-08-05T00:00:00"` — not a bare date. `scripts/run_backtest.py`'s
`_fetch_price_history()` parsed dates with:

```python
d = datetime.strptime(row["date"], "%Y-%m-%d")
```

`strptime` with a date-only format string raises `ValueError` on a string
that includes a time component. That exception was caught by a broad
`except (KeyError, ValueError, TypeError): continue` — written to
gracefully skip a handful of genuinely malformed rows, but it ended up
silently skipping EVERY row, since every single one hit the same
mismatch. The result: an empty list, with no signal that anything had
gone wrong — precisely the kind of silent, misleading failure this
project's own conventions (see `agents/cycle_health.py`) exist to catch
at the aggregate level, but this was a parsing bug inside a single
function, invisible to that machinery.

## The fix

Replaced the rigid `strptime` format with `datetime.fromisoformat()`,
which correctly handles the actual variety of ISO 8601 strings a pandas
`Timestamp.isoformat()` can produce — with or without a time component,
with or without a timezone offset:

```python
d = datetime.fromisoformat(row["date"]).date()
```

Verified against all three realistic variants directly:
`"2026-08-05T00:00:00"`, `"2026-08-05T00:00:00-04:00"` (timezone-aware),
and `"2026-08-05T00:00:00.000000"` (with microseconds) — all parse
correctly.

## Testing

`tests/test_run_backtest.py` — new file, 6 tests:
- Direct regression test proving the exact bug is fixed: 2 rows in,
  2 rows out (not 0)
- A separate test for the timezone-aware variant specifically, since
  it's a genuinely different string shape
- Malformed-row handling still works correctly (genuinely bad rows are
  still skipped, not everything)
- 3 tests for `_resolve_price_ticker()`'s existing behavior (explicit
  override, auto-resolution via `config/watchlist.py`'s ticker mappings,
  and the fallback-to-asset-itself case)

**586 tests total, all passing.** This is a good example of why live
verification matters even after extensive synthetic testing: every
existing test for this script used hand-constructed fake data with
whatever date format the test author assumed — none of them happened to
reproduce the EXACT string shape the real connector actually produces.
Only running it against the real pipeline surfaced the mismatch.

## A second real finding from the same live session: overlapping windows

Once the date-parsing fix let a real backtest run end to end, the user
re-ran it with `--step-days 7` (to better match Initial Jobless Claims'
weekly reporting cadence) while leaving the default `--forward-days 20`.
That combination means consecutive test dates' 20-day return windows
overlap by 13 days — the resulting "samples" share most of their price
history and are NOT statistically independent, but nothing in the tool
flagged this. `agents/backtest_engine.py`'s significance threshold
formula assumes independent samples, so it was silently understating the
true bar for genuine significance whenever windows overlapped.

**Fixed at the engine level, not just in this one script**:
`agents.backtest_engine.run_backtest()` now computes the average gap
between consecutive test dates and flags `windows_overlap=True` whenever
that gap is smaller than the forward-return window. `BacktestResult.interpretation()`
appends a clear caveat explaining exactly what this means and what to do
about it (widen `--step-days` to at least the forward window for a
cleaner test). Since `scripts/run_backtest.py` already prints
`result.interpretation()`, this caveat now appears automatically in every
future run with no changes needed to the script itself — and it applies
to every current and future caller of the engine, not just this one
command-line tool.

4 new tests in `tests/test_backtest_engine.py` prove: the caveat fires
correctly when the gap is smaller than the window (reproducing the user's
exact scenario), does NOT fire when the gap is at or above the window,
handles the empty/insufficient-data edge case, and computes the average
gap correctly for irregularly-spaced dates. **590 tests total.**

## A third real finding from the same session: no rate-limit pacing

Comparing the user's two identical `--step-days 7` runs directly: the
first got a usable signal reading for 240 of 261 dates; the second, same
exact command, only 220 of 261. `scripts/run_backtest.py` fired all ~261
FRED requests in a tight loop with zero delay between them — a real gap I
had explicitly flagged as a risk earlier ("I haven't built in any
rate-limit pacing... let me know and I can add a delay if so") but hadn't
fixed proactively.

**Fixed**: a configurable `--request-delay` (default 0.6s, a reasonably
conservative default based on FRED's generally-documented limits — NOT
verified against a live response from this development environment,
which has no network access) now paces every FRED-based signal's request
loop. Seasonality (which makes no network requests at all) is correctly
exempted — proven directly with a test showing zero `time.sleep()` calls
for that signal, alongside a separate test proving the exact expected
number of sleep calls (and the exact configured delay) for a FRED-based
one.

The pacing decision itself was extracted into a small, directly testable
`_needs_fred_pacing()` function, matching the same pattern already used
for `_resolve_price_ticker()`, rather than left as an untestable inline
expression buried in `main()`. **594 tests total.**
