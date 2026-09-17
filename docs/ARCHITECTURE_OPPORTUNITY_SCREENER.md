# The opportunity screener — many assets, ranked, not a fixed list

## What this adds, and what it honestly is not

Every script built before this took an explicit, manually-chosen asset
list (`--assets "AAPL:AAPL,SPY:SPY"`). This adds a genuine screener:
scan many assets across equities, commodities, FX, and crypto, and rank
them by a real signal, so the platform can surface candidates instead of
requiring them to be hand-picked every time.

**Read this before using the word "probability" anywhere near this
tool's output.** `agents/opportunity_screener.py` ranks by a
**conviction score** — the strength of a real, fast RSI/MACD/SMA-based
technical read (`agents.trade_scoring.build_synthetic_technical_report()`,
already built and tested elsewhere in this platform) combined with its
own confidence. This is deliberately NOT a rigorously backtested
win-probability. Computing that properly, per asset, means running
`agents.strategy_backtest.simulate_strategy()` — real simulated trades,
real historical performance — which is far too slow to do for hundreds
of assets in one screening pass (the same honest scope note already
applies to `scripts/run_backtest_all.py`). A high conviction score here
means "a real, fast technical signal is currently strong" — it is a good
**candidate for deeper backtesting**, not a validated winner. Run
`scripts/run_strategy_backtest.py` against anything promising before
sizing it with real conviction.

## What's reused vs. what's new

Reused entirely, no duplicated logic: the platform's existing curated
asset universe (`config/watchlist.py`'s commodity/FX/crypto tickers,
`config/sp500_tickers.py`'s 357 large-cap equities),
`agents/trade_scoring.py`'s technical scoring,
`agents/portfolio_construction.py`'s vol-target weighting and
constraints, and `agents/execution_engine.py`'s rebalance planning and
submission.

New: `agents/opportunity_screener.py`'s `screen_asset()` (scores one
asset from its own real price history, `None` for insufficient data —
never a fabricated score) and `rank_opportunities()` (filters by minimum
confidence, sorts by conviction descending, stable on ties — not
shuffled).

## `scripts/run_screener.py`

```
python scripts/run_screener.py
python scripts/run_screener.py --asset-classes commodity,fx,crypto --top-n 5
python scripts/run_screener.py --max-equities 100 --min-confidence 50 --build-portfolio
```

Scans, ranks, prints the top candidates. `--build-portfolio` turns the
ranked list into a real vol-target allocation and a real rebalance plan
against your actual (paper) account — `--submit` on top of that actually
places it. Same safety model as everywhere else: dry-run remains the
default even with `--submit` available, and there is no live-trading
flag anywhere in this file.

`--max-equities` defaults to 50, not the full 357 — scanning everything
is a lot of real Yahoo requests, paced (`--request-delay`) to avoid
rate-limiting, the same lesson already learned and fixed for FRED
requests earlier in this project.

## Update: excluded candidates surfaced as a genuine, full-detail section

The critical fix above (below) correctly excludes commodity/FX
candidates from the executable portfolio — but the original version
only listed their bare names. Someone who wants to manually trade one of
those candidates on a different platform (a real forex or futures
broker, since Alpaca can't) needs the same detail the main ranking shows
— bias, confidence, own volatility, conviction — not just a name to
look up elsewhere.

`--build-portfolio` now prints a dedicated `=== Manual Trading
Candidates ===` section with the identical table format as the main
ranking, for exactly the excluded commodity/FX (and any other
non-tradeable class) candidates. Proven directly: a real
`NZD/USD`/`Natural Gas` scenario shows both appearing with full detail
in their own section, confirmed absent from the executable allocation
either way, and a direct check that each row actually contains every
column (direction, bias, confidence, volatility, conviction) rather than
just a name.

## Update: a critical fix — non-tradeable asset classes were reaching the order-building step

Testing `--diversify --build-portfolio` with real data produced a
rebalance plan including orders like `NZD/USD BUY 29138.33` and
`Natural Gas BUY 901.87` — mathematically correct given the dollar
allocation, but for asset classes Alpaca's Trading API cannot trade
under any circumstances. Confirmed via research: Alpaca supports US
equities and crypto only — no forex, no commodities, no futures. Had
`--submit` been used on that exact result, every one of those orders
would have been rejected, or worse, an undefined failure. This is the
most severe finding in this module's history — not a ranking-quality
issue, a correctness issue that could have generated invalid live order
attempts.

**The fix**: `ALPACA_TRADEABLE_ASSET_CLASSES = {"equity", "crypto"}`,
checked explicitly before `--build-portfolio` constructs anything.
Commodity and FX candidates still appear in the SCREENING output — that
signal is real and useful regardless of whether this specific broker can
act on it — but are now explicitly, honestly excluded from the target
allocation and rebalance plan, with a clear message naming exactly which
candidates were excluded and why, rather than silently dropped or
(the original bug) silently included as if they were tradeable.

Proven directly with the user's exact real scenario reconstructed:
commodity and FX candidates confirmed to still appear in the ranked
output, confirmed absent from the target allocation section, and the
zero-tradeable-candidates edge case (every ranked result being
commodity/FX) confirmed to stop cleanly rather than build an empty or
broken plan.

## Update: fairness confirmed, diversification added as a separate, deliberate choice

The open question from the previous update is resolved: the real
volatility figures behind a live top-10 result (checked directly via
`annualized_vol_pct`, now exposed in the output) all looked realistic
and consistent with each name's actual, well-known character — nothing
suspiciously low that would have signaled a remaining bug. The
volatility-normalized scoring is working correctly.

What that live run actually revealed is a real, separate distinction: a
**fair** ranking and a **diversified** one are genuinely different
goals. A fair ranking can still legitimately return one asset class
almost entirely, if that class simply has more or stronger genuinely
trending assets than others *right now* — that's an honest reflection
of current conditions, not a bug to fix away.

`agents.opportunity_screener.rank_opportunities_by_class()` adds
diversification as an explicit, separate, opt-in choice —
`scripts/run_screener.py --diversify --top-n-per-class 3` guarantees
representation from every asset class scanned, rather than letting a
global top-N concentrate in whichever class is currently strongest.
Reuses `rank_opportunities()` for the actual filter/sort logic within
each class, no duplicated logic. Verified directly, twice: a unit test
proves representation is guaranteed even when one class's conviction
scores are far higher than another's, and a full CLI-level test with
realistic mixed-asset mocked data confirms commodity, FX, and equity
candidates all appear together even when the equities' raw conviction
scores are a fraction of the commodity/FX ones.

## Update: the fix verified, but a real, honest open question remains

After the fix, a real re-run across the same universe still returned a
top 10 that was 100% equities — the flat-normalization bug being fixed
(proven directly, twice, including at the full CLI level with controlled
synthetic data) did not, on its own, produce a visibly more diversified
real-world result.

**Two honest explanations, not one confirmed answer.** The most likely
one: this may genuinely be real, not a remaining bug. Individual equities
are well-documented in academic finance (stock-level momentum is a
heavily studied factor going back to Jegadeesh & Titman's foundational
research) to exhibit more persistent, company-catalyst-driven trends,
even relative to their own volatility, than broad FX pairs or commodity
futures — which tend to be macro-driven and comparatively
mean-reverting. A volatility-adjusted screener genuinely finding more
signal in individual stocks than in DXY or EUR/USD would not be
surprising. But this has NOT been independently confirmed — it's a
defensible, evidence-consistent explanation, not a proven one.

**What was added to let this be checked directly rather than trusted
blindly**: `ScreenedOpportunity` now carries the asset's own
`annualized_vol_pct` — the actual number the normalization divides
by — printed in `scripts/run_screener.py`'s output table. If a specific
equity's own volatility figure looks suspiciously low (which would
artificially inflate its score even after the fix), that's directly
visible now instead of hidden inside the calculation. Re-running on a
different day, and checking whether the same equity-heavy pattern
persists or was specific to that day's data, is the natural next check.

## Update: a real cross-asset-class ranking bias, found via live testing, fixed

A real screener run across equities, commodities, FX, and crypto came
back with a top 10 that was **100% volatile growth stocks** — zero
commodities, zero FX, zero crypto, despite scanning all of them. Every
result also showed the identical `confidence=90.0`, which was the tell
that the ranking wasn't actually differentiating fairly.

**Root cause**: the original design ranked by
`build_synthetic_technical_report()`'s own `bias_score`, which comes
from `agents.technical_indicators.trend_score()` — a flat 5%
normalization threshold applied uniformly to every asset. A 5% SMA
separation is a routine, unremarkable occurrence for a volatile growth
stock, but a genuinely rare, significant one for a major FX pair.
Comparing both against the same flat bar meant volatile assets
constantly hit the scoring ceiling while calmer ones almost never did —
not because they had better opportunities, but because the scoring
method structurally couldn't score anything else as highly.

**The fix**: `agents.technical_indicators.volatility_normalized_trend_score()`
— a new, additive function (the existing `trend_score()` is completely
unchanged, still used as before by Chief Equity Analyst and the Trade
Decision Engine, where cross-asset-class fairness isn't the relevant
question). Instead of a flat percentage, it normalizes by the asset's
OWN annualized volatility, scaled to the comparison window via the
standard volatility-scales-with-square-root-of-time convention. A move
equal to what's NORMAL for that specific asset scores as strong,
regardless of whether that asset is a calm currency pair or a volatile
growth stock.

**Proven directly, twice**: a unit test gives the exact same price move
to a "calm" and a "volatile" asset (same SMA separation, different
`annualized_vol_pct`) and confirms the calm one scores higher. A full
CLI-level test goes further — five real assets (FX, commodity, three
growth stocks) are all given the IDENTICAL underlying trend strength,
differing only in their day-to-day noise. After the fix, the calm assets
(EUR/USD, Gold) correctly rank above all three volatile stocks — the
complete opposite of what the original, biased version produced for the
exact same inputs.

## Verified end-to-end with mocked data

A synthetic uptrend (Gold) and downtrend (Silver) were screened, and the
tool correctly identified Gold as the highest-conviction long and Silver
as a genuine short, ranked in the right order by conviction magnitude.
The `--build-portfolio` path was verified separately: the top-ranked
candidates correctly fed into `volatility_target_weights()`, producing a
real allocation, and the script correctly stopped cleanly when no
Alpaca credentials were available rather than crashing.

## Testing

12 tests in `tests/test_opportunity_screener.py` (including the
cross-asset fairness regression test above) plus 8 new tests in
`tests/test_technical_indicators.py` for
`volatility_normalized_trend_score()` itself: the price-history
shape conversion (oldest-first tuples to newest-first dicts) proven
directly, insufficient-history correctly returning `None`, a genuine
uptrend/downtrend correctly identified as long/short, the conviction
score formula verified against a hand computation, and `rank_opportunities()`
proven on minimum-confidence filtering, descending sort order, `top_n`
truncation, empty input, and tie-stability, plus a direct check that
`annualized_vol_pct` is genuinely populated with a real, positive
number. **741 tests total, all passing.**

## A second real environment fix, found on the same real run

`test_data_health_refresh_button_does_not_crash_offline` timed out at
30 seconds on a real machine with network access — not a platform bug.
That test's own docstring assumes no network (this codebase's sandboxed
CI environment), where every data source fails instantly. On a real
network, refreshing many real data sources at once — even when every one
correctly, gracefully degrades — takes real wall-clock time a
network-less environment never has to wait through. Fixed by raising
just this test's timeout to 90s; the button's actual behavior (never a
crash) is unchanged.

## A separate, real fix made while restoring this environment

While rebuilding the sandbox this was developed in, `pytest` surfaced 25
genuine failures in `tests/test_dashboard_pages.py` — not a platform bug,
a real Streamlit version behavior change (1.61.1 now installed vs. an
older version previously in use): `AppTest.from_file()` started resolving
relative paths against the calling test file's own location, not the
working directory. Fixed by resolving every path to an absolute one
before passing it in, rather than leaving it environment-dependent.
