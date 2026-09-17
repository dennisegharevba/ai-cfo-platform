# Institutional Market Regime Filters + Precious Metals USD Fundamentals

## Two related upgrades in one delivery

Per an explicit request with two parts:
1. **Gold and other metals should be fundamentally backed, not just COT
   alone** — using the same US-Dollar-related fundamentals that drive USD
   itself, since Gold (and other precious metals) are priced in dollars.
2. **Institutional Market Regime Filters** — Federal Reserve Policy, US
   10-Year TIPS Real Yield, US 10-Year Treasury Yield, and VIX must be
   evaluated alongside Chief Macro Officer's existing factors and act as a
   high-priority CONFIRMATION layer, adjusting confidence (never
   overriding direction) before any trade recommendation.

Both reuse infrastructure that already existed rather than building
parallel systems: the regime filters reuse the Institutional Relationship
Engine's alignment classification (originally built for commercial vs.
speculative COT, now orphaned since Commercial Traders were removed — see
`docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md`); precious metals reuse
Chief Macro Officer's own FRED-backed datasets rather than fetching the
same series a second time.

## `agents/institutional_market_regime.py` — the new scoring module

Four independently-scored components, each on this platform's standard
-100..+100 scale (for consistency with every other scoring function):

| Component | Real data source | What's honestly NOT modeled |
|---|---|---|
| Fed Policy | FRED `FEDFUNDS` (Fed Funds Rate trend) | FOMC statement text, Dot Plot, SEP, Powell's tone, CME FedWatch expectations — all optional manual inputs, defaulting to no adjustment when not supplied |
| Real Yield | FRED `DFII10` (10Y TIPS), monthly bps change | — |
| Treasury Yield | FRED `DGS10` (shared with Chief Bond Strategist), weekly bps change | — |
| VIX | FRED `VIXCLS`, current level | — |

**Honest scope on Fed Policy**: the spec's full wishlist (Dot Plot, SEP,
Powell's press conference tone, CME FedWatch market-implied expectations)
has no free structured live source — these would need NLP over Fed
communications or a paid data feed neither of which this platform
integrates. The BASE score is genuine and live (the actual Fed Funds Rate
trend); `fed_tone` and the surprise-factor inputs (`expected_decision`/
`actual_decision`/`surprise_magnitude`) are OPTIONAL parameters that
default to having no effect — a human reading an FOMC statement could
supply `fed_tone="dovish"` and it would apply the spec's exact point
adjustment, but nothing is guessed or fabricated when they're absent.

**Combining components**: `combine_regime_scores()` uses the spec's exact
weights (Macro 40%, Fed Policy 20%, Real Yield 15%, Treasury Yield 15%,
VIX 10%), RENORMALIZED over only the components actually available — a
missing component contributes zero weight, never a fabricated neutral
placeholder, matching this platform's "confidence reflects real data
coverage" rule established since Phase 1.

**Display scale**: internally everything is -100..+100 for consistency
with the rest of the codebase; `InstitutionalMarketRegime.display_score()`
converts to the spec's own 0-100 scale, and `display_band()` applies the
spec's exact 7-band labels (Strong Bullish through Strong Bearish) purely
for presentation — the internal scale is what all the math and tests use.

**VIX above 35** triggers the spec's exact warning message
("Extreme volatility regime. Long equity setups should be avoided.") and
escalates the containing report's `risk_level` to HIGH.

## A real bug found and fixed during my own review

`build_regime_reasoning()`'s "Insufficient data" fallback was DEAD CODE —
the function always appended a closing "positioning favors buying/selling/
waiting" sentence regardless of whether any actual component was
available, so the `parts` list could never be empty and the fallback
branch could never trigger. Caught by a test
(`test_reasoning_handles_all_missing_gracefully`) that actually failed on
first run rather than being written to match whatever the code happened
to do. Fixed by checking for an empty `parts` list before appending the
closing sentence, not after.

## Integration into Chief Macro Officer: confirmation, never override

Per the spec's own "Trade Filter Rule" ("reduce the confidence score
rather than rejecting the trade outright"), the regime is a PEER-LEVEL
component alongside the 16 Macro factors — NOT folded into the Macro
category average — combined via `combine_regime_scores(macro_score=...)`.
The regime's own bias is then compared against the Macro category's bias
using `agents.institutional_relationship.classify_alignment()` (the exact
same Full-Alignment/Mild-Divergence/Strong-Divergence classifier
originally built for the commercial/speculative COT relationship), and
`apply_confidence_adjustment()` applies the existing +15/-10/-25 confidence
shift. **This is a deliberate reuse, not an accident**: the mechanism
already existed, was already tested, and does exactly what this spec asks
for — a secondary signal that adjusts trust in a primary signal without
ever flipping its direction. `tests/test_chief_macro_officer.py`'s
`test_regime_conflicting_with_macro_reduces_confidence` proves the bias
direction genuinely never changes even under maximum regime disagreement.

**A real mathematical finding during test-writing**: with the 16 Macro
factors saturated at their maximum ±100 score, the regime's 60% combined
weight can mathematically NEVER flip the sign — even every regime
component at its most extreme bearish reading only contributes
`0.2×(-100) + 0.15×(-20) + 0.15×(-15) + 0.10×(-100) = -35.25`, which
Macro's own `0.4×100 = +40` always outweighs. The first version of this
test assumed a sign flip that was mathematically impossible given a
saturated macro score, and failed correctly — fixed by testing with a
realistic, non-saturated macro reading instead, which is also more
representative of how the platform behaves in practice (a fully-saturated
16-factor average is rare).

## Precious metals: fundamentally backed by USD-related data

Per the explicit reasoning "Gold is priced in dollars" — Gold (and, by the
same logic, Silver/Platinum/Palladium) now have real
`FundamentalFactor` entries in `agents/chief_commodity_fundamentals_officer.py`:

- US 10Y Real Yield (falling = bullish — lower opportunity cost of holding
  a non-yielding asset)
- Trade-Weighted Dollar Index (falling = bullish — a weaker dollar makes
  dollar-priced gold cheaper elsewhere)
- Federal Funds Rate (falling = bullish — easier policy)

**These reuse Chief Macro Officer's EXACT dataset keys** (`KEY_REAL_YIELD`,
`KEY_DOLLAR_INDEX`, `KEY_FED_FUNDS`) via a new `override_key` field on each
factor spec tuple, rather than fetching the identical FRED series again
under a Gold-namespaced key. `tests/test_chief_commodity_fundamentals_officer.py`'s
`test_gold_reuses_chief_macro_officers_exact_dataset_keys` proves this
directly — Gold's `required_dataset_keys()` returns the SAME three keys
Chief Macro Officer registers, not a separate copy.

**A real functional gap found and fixed while wiring this up**:
`register_commodity_fundamentals_sources()` only knows how to build EIA
connectors, so it correctly SKIPS any factor with an `override_key` — but
that means calling it alone for Gold registers nothing at all (proven by
`test_register_commodity_fundamentals_sources_is_a_noop_for_gold`). Every
caller that runs Commodity Fundamentals for a precious metal (the demo
script, the dashboard, `scripts/run_daily_cycle.py`) must ALSO call
`agents.chief_macro_officer.register_macro_data_sources()` — which is
idempotent (skips already-registered keys), so calling it is always safe
regardless of whether Macro already ran earlier in the same cycle. This
was missing in the initial wiring and would have made precious metals
always show zero confidence in the real scheduled cycle even though the
scoring logic itself was fully capable — caught by re-running the demo
script live and noticing the stale "Gold has no factors configured"
framing no longer matched what the code actually does, not assumed correct.

Silver, Platinum, and Palladium share Gold's exact factor list (same USD
sensitivity) — `COMMODITY_FACTOR_SPECS["Silver"] is COMMODITY_FACTOR_SPECS["Gold"]`
(same list object, not a copy). Mine production, central bank gold buying,
ETF flows, and industrial/jewellery demand remain absent — no free
structured live source for any of them, same honest-scope rule as
everywhere else in this platform.

## Testing

- 42 tests for `agents/institutional_market_regime.py` (every scoring
  function's bands, the combination weighting and renormalization, display
  conversion, market impact table, reasoning generation — including the
  dead-code bug found and fixed)
- 12 tests (rewritten) for Chief Macro Officer's regime integration
  (confirmation boosts confidence, conflict reduces it without flipping
  bias, VIX extreme warning and risk escalation, full serialization)
- 14 tests (expanded) for Chief Commodity Fundamentals Officer's precious
  metals support (bullish/bearish USD scenarios, exact key reuse proof,
  the registration no-op finding, shared factor list across all 4 metals)
- 2 new dashboard interaction tests specifically exercising Gold through
  the actual UI (not just the default "Crude Oil" text input value)
- 437 tests total, all passing; both `demo_agents.py` and
  `demo_commodity_fundamentals.py` re-run live end-to-end, correctly
  showing graceful degradation with no network access in this environment

## What's next (not yet built)

- Fed tone/surprise as anything other than an optional manual input (a
  real NLP-over-FOMC-statements pipeline, or a paid CME FedWatch feed,
  would be substantial standalone projects)
- Sentiment, Risk, Seasonality categories on the same `score_category()` engine
- The full "hedge fund research terminal" dashboard redesign
- The "Explain Every Decision" auto-explanation generator at the Strategy
  Officer level (the regime's own `build_regime_reasoning()` is a first,
  narrower version of this idea, scoped to just the regime layer)
