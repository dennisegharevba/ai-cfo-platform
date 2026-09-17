# "Explain Every Decision" — the decision explanation generator

## What this adds

Per the original upgrade spec's explicit requirement: "After generating
the final bias, produce a detailed explanation showing: Why each factor
is bullish, bearish, or neutral. Which factors had the greatest
influence. Which factors conflicted with the final decision. The
strongest risks to the current bias. What future events could
invalidate the analysis."

`ChiefStrategyOfficer.synthesize()` now produces a `decision_explanation`
field on every `StrategyReport`, covering all five of the spec's points
in one deterministic paragraph — built entirely from template strings
over data the synthesis had already computed, no LLM call, consistent
with every other narrative field in this platform (`trade_thesis`,
`investment_committee_summary`, `institutional_commentary`).

## Why this was the natural next step after the six scoring categories

With Macro, Commodity Fundamentals, COT, Sentiment, Seasonality, and Risk
all producing real `AgentReport`s with real `factor_breakdown` detail,
`ChiefStrategyOfficer` finally had everything the spec's explanation
requirement asks for already sitting in its own `synthesize()` method —
this is a genuinely small, well-scoped addition on top of substantial
existing infrastructure, not a new subsystem.

## How each of the spec's five points is derived

1. **Why each factor is bullish/bearish/neutral** — iterates every
   CONTRIBUTING department's own `bias_score`, classifying it the same
   way `bias_from_score()` classifies the overall bias (>15 bullish, <-15
   bearish, else neutral) for direct comparability.
2. **Which factors had the greatest influence** — ranks departments by
   `effective_weight` (`department_weight * confidence/100`), the EXACT
   same value already computed in the main synthesis loop and used to
   calculate the overall `bias_score` — not re-derived or approximated,
   the real number that actually moved the outcome.
3. **Which factors conflicted with the final decision** — any
   contributing department whose `bias_score` sign is opposite the
   overall bias's sign, with both sides required to be meaningfully
   non-neutral (>15 in magnitude) to avoid flagging noise near zero as a
   "conflict."
4. **Strongest risks** — the top 3 entries from the already-deduped,
   already-capped `risks` list `synthesize()` builds.
5. **What could invalidate the analysis** — reuses the existing
   `invalidation_notes` field (Phase 7), stripping its "Thesis is
   weakened if:" prefix for a smoother read within the explanation
   paragraph.

Every one of these draws from data `synthesize()` was already computing
for other fields — nothing new was fetched or estimated.

## `contributing_weighted`: a small but necessary addition to the main loop

To rank departments by their REAL effective weight (point 2 above)
without recomputing it a second time (and risking the two computations
drifting apart), `synthesize()`'s main loop now also appends
`(department, bias_score, effective_weight)` tuples to a new
`contributing_weighted` list, alongside the existing parallel
`bias_scores`/`weights`/`confidences` lists it already built. This is the
only structural change to the existing synthesis loop; everything else
(the actual weighted-mean/disagreement math) is completely untouched.

## Dashboard

`dashboard/pages/3_Strategy_Synthesis.py` shows the explanation in a
collapsed "Explain This Decision" expander, right after Institutional
Commentary. Verified directly — not assumed to render just because the
page didn't raise an exception — by extending the existing execution-
readiness/commentary interaction test to also check the expander's label
and its actual rendered text.

## Testing

- 7 new tests in `tests/test_chief_strategy_officer.py`: every
  department listed with its bias, greatest-influence ranking correctly
  reflects effective weight (not just raw bias_score), conflict detection
  fires when departments genuinely disagree and correctly reports "no
  conflict" when they agree, risks/invalidation content is present, the
  empty-reports edge case degrades gracefully, and `to_dict()`
  serialization includes the new field
- 1 extended dashboard test, verified with real rendered content
- 476 tests total, all passing; `scripts/demo_strategy_officer.py` re-run
  live, producing a genuinely coherent, accurate explanation matching its
  own underlying data exactly (verified by reading the actual printed
  output, not assumed correct from the implementation alone)
- Zero regression: the full existing test suite (469 tests before this
  addition) passes completely unchanged

## What's still not built

- The full "hedge fund research terminal" dashboard redesign (Market
  Overview header, per-category tables laid out per the spec's exact
  visual mockup, Final Investment Committee table) — this remains the
  one substantial piece of the original spec not yet attempted, and is a
  much more open-ended UI/UX task than anything built so far
- Wiring `agents/market_regime.py`'s dynamic weighting into
  `ChiefStrategyOfficer`'s actual department-weighting logic
