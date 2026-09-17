# Three self-identified improvements, fixed: cycle health, dynamic weighting, verification tooling

This covers the three concrete, immediately-actionable items from a
broader self-assessment ("what can I improve on this machine") — the
fourth item (real backtesting) is deliberately NOT here, since it's a
substantial enough undertaking to deserve its own dedicated scoping
conversation rather than being squeezed in alongside smaller fixes.

## 1. Cycle health detection — catching silent, systemic degradation

**The gap**: `scripts/run_daily_cycle.py` already logged
`"N of M watchlist entries failed this cycle"` — but that only counts
HARD CRASHES (exceptions). Given this platform's own core design
philosophy — never crash, always degrade gracefully to zero confidence
on missing/bad data — the far more likely real-world failure mode is
everything completing "successfully" while silently returning near-zero
confidence across most or all entries (an expired FRED key, a blocked
network host, a broken shared connector). The old crash-only check would
report `"0 of 357 failed"` in exactly that scenario — technically true,
dangerously misleading.

**The fix**: `agents/cycle_health.py`'s `assess_cycle_health()` looks at
the FULL results list (not just exceptions) and distinguishes NORMAL
partial degradation (a handful of tickers with bad data this cycle —
routine in any live system) from a SYSTEMIC pattern (most/all entries
degraded at once, almost always one shared root cause). Two independent
thresholds: ≥25% hard-crashed, or ≥50% completed with confidence below
10/100. Either fires a clear `⚠️ SYSTEMIC ISSUE LIKELY` message with a
plain-language explanation, both in the printed cycle summary and in the
logs.

Wired into `scripts/run_daily_cycle.py`'s `main()` for both watchlists.
Verified LIVE against this genuinely network-isolated sandbox — the real
daily cycle correctly flagged itself: *"27 of 35 entries (77%) completed
with near-zero confidence... this pattern usually means one shared
cause..."* — exactly the scenario this was built to catch, and it
correctly still counted the 8 Seasonality-covered assets as healthy,
since that one department needs no network access at all.

## 2. Dynamic regime weighting — actually wired in, not just built

**The gap**: `agents/market_regime.py` (real FOMC-week / earnings-season
detection, tested standalone) existed but had zero references anywhere
in `agents/chief_strategy_officer.py`. The "dynamic weighting" from the
original spec was still running on static weights only.

**The fix**: `ChiefStrategyOfficer.synthesize()` gained an optional
`reference_date` parameter (defaults to today). Internally, it classifies
the active regime ONCE per synthesis call and applies it as a multiplier
on top of each department's static default weight — but ONLY for
departments with a genuine, unambiguous category match
(`DEPARTMENT_TO_REGIME_CATEGORY`: `"Chief Macro Officer"` →
`"Macroeconomic"`, `"Chief Equity Analyst"` → `"Equity Fundamentals"`).
Every other department's weight is completely untouched — no guessed
category mappings invented just to give more departments a multiplier.

Proven with real outcome-shifting tests, not just "the function runs":
the exact same pair of opposing reports produces a genuinely DIFFERENT
`bias_score` in an earnings-season month vs. a normal month
(`test_earnings_season_boosts_equity_analyst_weight_and_shifts_the_outcome`),
and the same for a monkeypatched FOMC week. A department outside the
regime mapping (Chief Bond Strategist) is proven to be byte-identical
across regimes.

**A latent test-fragility risk caught and documented, not silently
patched**: since `synthesize()` now defaults to `date.today()`, any
EXISTING test asserting an exact bias_score/weight involving Chief Equity
Analyst could theoretically start failing in a real earnings-season month
(Jan/Apr/Jul/Oct) that it wasn't failing in when written. Checked
directly — no existing test does this — and rather than touching all 32
existing `synthesize()` call sites for a currently-nonexistent problem, a
clear comment was added to `tests/test_chief_strategy_officer.py`
documenting the consideration for future test-writers, with the new
regime-specific tests (`tests/test_chief_strategy_officer_regime_weighting.py`)
demonstrating the correct pattern (always pass an explicit
`reference_date` when asserting exact numbers tied to a regime-mapped
department).

## 3. Verification tooling — extended to cover everything currently "unverified"

**The gap**: this platform has accumulated several "best-effort, not
verified against a live source" mappings over its build (CFTC market
names, FX/commodity/crypto Yahoo tickers, EIA API routes) — each a
reasonable individual judgment call at the time, but never actually
checked against a real API from an environment with network access.

**The fix**: `scripts/verify_watchlist_markets.py` — previously only
covering CFTC market names and equity tickers — now also checks every
Yahoo Finance ticker (`config/watchlist.py`'s `FX_YAHOO_TICKERS`,
`COMMODITY_YAHOO_TICKERS`, `CRYPTO_YAHOO_TICKERS`) and every EIA API
route (`agents/chief_commodity_fundamentals_officer.py`'s
`EIA_ROUTE_SPECS`) against the real APIs, reporting exactly which ones
(if any) don't resolve, with a pointer to where to fix each kind. The
EIA check gracefully skips (not crashes) if `EIA_API_KEY` isn't set, the
same pattern the existing SEC ticker check already used for
`SEC_USER_AGENT`.

**This tool needs YOU to actually run it** — this sandbox has zero
network access, so every check here reports "BAD" purely because nothing
can reach the internet at all, not because the mappings are actually
wrong. Run `python scripts/verify_watchlist_markets.py` with real network
access (and a real `EIA_API_KEY` for the EIA portion) to get a real
answer.

## Testing

- 11 tests for `agents/cycle_health.py` (normal degradation vs. systemic,
  both threshold types, edge cases like malformed result dicts)
- The new health check verified live against the real, network-isolated
  daily cycle
- 5 tests for dynamic regime weighting, all using explicit
  `reference_date` for determinism — including direct proof the weighting
  change genuinely shifts outcomes, not just a cosmetic multiplier
- Verification script extended and confirmed to run correctly end-to-end
  (gracefully reporting failures given this sandbox's lack of network
  access, rather than crashing)
- 539 tests total, all passing, zero regression

## What's still not done

- **Real backtesting against historical data** — deliberately not
  attempted here. This is the single largest remaining gap and deserves
  its own dedicated scoping conversation (historical data source,
  replay methodology, what "success" even means for a research-only
  platform that never places trades) rather than being rushed in
  alongside three smaller, well-bounded fixes.
- Retail positioning, options positioning, ETF flows, MOVE/GVZ/OVX — no
  free data source found; unchanged from previous assessment.
