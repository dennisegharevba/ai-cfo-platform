# A real data integrity bug: 8-year-stale Revenue data from SEC EDGAR

## How this was found

The user's live verification of Chief Equity Analyst (finally unblocked
after fixing an unrelated `SEC_USER_AGENT` configuration issue — see
below) showed something that looked fine at a glance but wasn't:

```
Diluted EPS is growing (latest=6.88 as of 2026-06-27)
Revenue is growing (latest=265595000000 as of 2018-09-29)
```

EPS is dated correctly — current, real, 2026. Revenue is dated
**2018-09-29**. Eight years stale. Both datasets reported
`quality_score: 100.0` and `validation_status: 'valid'` — nothing in the
pipeline flagged this as wrong, because from the connector's point of
view, nothing WAS wrong: it successfully fetched real data. It just
fetched the wrong tag's real data.

## Root cause

`connectors/sec_edgar_connector.py` queries SEC's XBRL companyconcept API
for a single hardcoded tag, `"Revenues"`. In 2018, ASC 606 (a revenue
recognition accounting standard) took effect, and many public companies
— Apple among them — switched which XBRL tag they file total revenue
under, from `Revenues` to
`RevenueFromContractWithCustomerExcludingAssessedTax` (or a close
variant). Apple's `Revenues` tag didn't disappear or start erroring — it
just stopped receiving new filings. Querying it in 2026 still returns a
perfectly well-formed, successfully-parsing response: the LAST thing ever
filed under that tag, from September 2018.

The connector's own docstring had actually anticipated this in general
terms ("some filers use RevenueFromContractWithCustomerExcludingAssessedTax
instead — check a company's actual filings if this tag comes back
empty") — but the real failure mode is worse than "comes back empty."
It comes back FULL, with genuinely real historical data, silently
mislabeled as current. No error, no empty-response check, would ever
catch this.

## The fix

`SecEdgarConnector` now accepts an optional `fallback_concepts` list.
`fetch()` tries EVERY candidate (the primary concept plus every
fallback) and keeps whichever one has the MOST RECENT filing date — not
simply "the first one that doesn't error." That distinction matters: a
naive try-primary-then-fallback-on-failure approach would never have
caught this bug, since the primary concept doesn't fail, it just returns
old data.

`connectors/sec_edgar_connector.py` now exports
`REVENUE_FALLBACK_CONCEPTS = ["RevenueFromContractWithCustomerExcludingAssessedTax",
"RevenueFromContractWithCustomerIncludingAssessedTax"]`, wired into every
call site that registers Revenue for Chief Equity Analyst:
`scripts/demo_equity_crypto_agents.py`, `scripts/run_daily_cycle.py`, and
`dashboard/pages/2_Department_Reports.py`. EPS was deliberately left
untouched — `EarningsPerShareDiluted` doesn't have a known equivalent
tag-migration issue, and adding fallback candidates without evidence of
a real problem would be an unfounded guess, not a fix.

## A separate, smaller thing fixed along the way: `.env` had a duplicate key

Before this bug could even be investigated, `SEC_USER_AGENT` showed as
unset despite the user having added it. The cause: two `SEC_USER_AGENT=`
lines existed in `.env` — one empty, one with a real value — and
whichever `python-dotenv` read last was winning (the empty one). Not a
code bug, just a configuration mistake, resolved by removing the
duplicate line. Documented here because it's a real class of thing worth
double-checking (`Get-Content .env | Select-String "KEY_NAME"`) if a
value that was "definitely added" still shows as empty.

## Testing

5 new tests in `tests/test_sec_edgar_connector.py`:
- Direct reproduction of the exact bug: a stale primary + a fresh
  fallback, proving the fallback correctly wins
- The reverse case: a genuinely-fresher primary correctly beats an
  unused/empty fallback (proving this isn't a blind "always prefer
  fallbacks" rule)
- Backward compatibility: a connector with no `fallback_concepts` (like
  EPS) behaves identically to the original implementation
- Every candidate failing still raises clearly, listing every concept
  tried
- `REVENUE_FALLBACK_CONCEPTS` is importable and contains the expected tag

601 tests total, all passing. All 3 real call sites updated and syntax-
verified; dashboard AppTest suite re-run to confirm the
Department Reports page change is safe.

## What this means for anyone who ran Chief Equity Analyst before this fix

Any prior live run's Revenue-based conclusions for a company that made
this tag transition (very common — ASC 606 affected the vast majority of
US public companies around 2018) were built on real but badly outdated
figures, silently reported as "latest" with full confidence. EPS was not
affected by this specific bug. Re-running after this fix will show
genuinely current revenue data.

## Update: a second, more significant bug found in the same investigation

Re-running Chief Equity Analyst after the fix above confirmed Revenue's
date was now correct (2026, not 2018) — but the overall bias was STILL
pinned at exactly `+100.0`, even with genuinely fresh, correct data. That
was the signal something deeper was wrong, not just stale data.

**Root cause**: the connector filtered candidate filings by FORM TYPE
alone (10-Q vs 10-K), sorted by end date, and took the most recent N —
but form type alone doesn't guarantee comparable reporting PERIODS. A
10-K (annual filing) commonly includes quarterly comparative figures
alongside the full-year total; a 10-Q sometimes reports 6-month or
9-month year-to-date cumulative figures alongside the standalone quarter.
None of this was checked — only the "end" date was tracked, never
"start." That means the "trend" being scored could genuinely be comparing
ONE QUARTER's EPS/Revenue against a FULL YEAR's EPS/Revenue as if they
were sequential, comparable data points — a huge, meaningless swing
driven entirely by reporting-period length, not real business
performance, and one that would clamp the trend score at its maximum
almost regardless of any normalization threshold, since the underlying
comparison itself was invalid.

**The fix**: `_period_days()` computes each entry's actual duration
(`end` minus `start`, both now captured from SEC's response). Entries
are bucketed into quarterly (~80-100 days) or annual (~350-380 days) —
never mixed — preferring quarterly when there are at least 2 (more
frequent, more granular data), falling back to annual otherwise. Entries
with an unparseable or in-between period length (6-month/9-month
year-to-date) are excluded entirely rather than guessed into either
bucket. If no consistent-period series can be formed at all, the
connector raises clearly — caught by the existing `DataIntegrityManager`
pattern the same way any other fetch failure is, degrading that dataset
to confidence 0 rather than crashing or silently returning an invalid
mixed series.

**8 more tests** in `tests/test_sec_edgar_connector.py`, including direct
proof that a single quarter + a single year (2 filings, 2 different
period lengths) correctly do NOT combine into one trend, that a filer
with insufficient quarterly data correctly falls back to annual, and that
data with genuinely no determinable period length raises clearly rather
than guessing. **604 tests total.**

## Update: a third bug, found via a diagnostic tool built specifically to investigate this

After the period-length fix, re-running still produced wildly different
results across consecutive runs for the same company on the same day —
`+100.0` with EPS $6.88, then `-100.0` with EPS $2.02, both claiming the
same `2026-06-27` date. Rather than guess at a third fix,
`scripts/debug_sec_edgar_raw.py` was built to dump SEC's raw response
directly, and the user ran it against real Apple data.

**What the raw dump showed**: the `2026-06-27` date genuinely has two
legitimate entries — a 272-day cumulative year-to-date figure ($6.88)
and a real 90-day single-quarter figure ($2.02) — confirming the
period-length fix correctly picks the real quarterly figure. But the
dump also showed something new: **many entries appear as EXACT
duplicates** (identical start, end, and value, 2-4 times each) —
apparently from SEC's feed including multiple filing/amendment
references to the same underlying fact.

Left undeduplicated, these repeats silently consumed slots in the
8-period comparison window — reconstructing the user's exact real data
and running it through the (already period-length-fixed) connector
reproduced the -100.0 clamp precisely: **4 duplicate entries consumed
half the window**, pushing a genuinely older quarter out and pulling in
a newer one instead — landing on a comparison between Apple's Q1 FY2025
(the holiday quarter, naturally the highest-EPS quarter of the year,
$2.40) and Q3 FY2026 (a summer quarter, naturally lower, $2.02) — a
-15.8% "decline" that was really just ordinary seasonal variation, not
a genuine business change, and clamped to -100.0 at the default 5%
threshold.

**The fix**: entries are now deduplicated by `(start, end, val)` before
any bucketing or slicing. Re-running the reconstructed real data after
the fix correctly reaches 7 distinct quarters (not 4 real ones padded to
8 with duplicates) and produces a genuinely sensible **+32.0%** trend —
consistent with Apple's real growth trajectory, not a seasonal artifact.

**2 more tests**, including a direct reproduction of the user's exact
real diagnostic data, proving the fix resolves the precise scenario
found live. **606 tests total.**

## An honest, still-open limitation

Deduplication resolves the specific bug found, but doesn't fully
eliminate the deeper concern it revealed: comparing the oldest and
newest of N quarterly periods can still land on two DIFFERENT fiscal
quarters (e.g. Q1 vs Q3) rather than a clean same-quarter,
year-over-year comparison, if the window size isn't an exact multiple of
4 or if any quarters are genuinely missing from SEC's data. A more
robust design might explicitly prefer same-quarter-year-over-year or
trailing-twelve-month comparisons for equity trend scoring specifically,
the same way seasonality is already treated as a first-class concept for
commodities elsewhere in this platform. Not attempted here — flagged
honestly as a real, deeper methodological question rather than papered
over.
