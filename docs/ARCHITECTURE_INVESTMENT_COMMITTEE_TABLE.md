# Final Investment Committee Table

## What this adds

Per the original upgrade spec's exact example:

```
Factor                    Bias      Weight    Confidence
Macro                     Bullish   30%       92%
Commodity Fundamentals    Bullish   25%       89%
Technical                 Bullish   15%       81%
Sentiment                 Neutral   10%       65%
COT                       Bullish   10%       72%
Seasonality               Bullish   10%       78%
Final Market Score: 82 / 100
Confidence: 91%
Overall Bias: Bullish
Investment Committee Recommendation: Long
```

`ChiefStrategyOfficer.synthesize()` now produces `committee_table` (a list
of per-department rows in this exact shape) and `committee_recommendation`
(the "Long"/"Short"/"Hold" line) on every `StrategyReport`.

## Built from data already computed, nothing re-derived

`committee_table` is computed directly from `contributing_weighted` — the
same `(department, bias_score, effective_weight, confidence)` tuples
already built for the "Explain Every Decision" generator (see
`docs/ARCHITECTURE_DECISION_EXPLANATION.md`) and used to calculate the
overall `bias_score` itself. The `weight_pct` column is that same
`effective_weight`, normalized to a percentage of the total across
contributing departments — so the column sums to (approximately) 100%,
matching the spec's own example exactly, using the REAL weighting that
actually produced the synthesis, not a separately-guessed approximation.
Rows are sorted by weight descending, matching how a real committee
summary presents its most influential inputs first.

An empty `contributing_weighted` (no department produced usable data)
correctly returns an empty table — never a fabricated row for a
department that didn't actually contribute.

## `committee_recommendation`: a research label, never a trade instruction

This platform has never placed a trade, in any phase, and this addition
doesn't change that. `committee_recommendation` deliberately reads "Long
(research view)" / "Short (research view)" / "Hold / No Trade (research
view)" — never a bare "Long"/"Buy"/"Sell" that could be mistaken for an
execution instruction. `test_committee_recommendation_never_a_bare_trade_instruction`
locks this in directly. The mapping:

- `execution_readiness == NO_TRADE` or `bias == NEUTRAL` → Hold / No Trade
- Bullish/Strongly Bullish → Long (research view)
- Bearish/Strongly Bearish → Short (research view)

## Dashboard

`dashboard/pages/3_Strategy_Synthesis.py` renders the table via
`st.dataframe`, immediately followed by the Final Market Score/
Confidence/Recommendation summary row — placed right after the "Explain
This Decision" expander. Verified directly (not assumed to render just
because the page didn't crash) by extending the existing execution-
readiness/commentary interaction test to also check for the "Final
Investment Committee" subheader and a real rendered dataframe.

## Testing

- 9 new tests in `tests/test_chief_strategy_officer.py`: weights sum to
  ~100%, rows sorted by weight descending, row field correctness, the
  empty-contributors edge case, all three recommendation bands, and the
  explicit "never a bare trade instruction" check
- 1 extended dashboard test, verified with real rendered content
- 487 tests total, all passing; `scripts/demo_strategy_officer.py`
  re-run live, producing output that matches the spec's example table
  format exactly

## What's still not built

- Wiring `agents/market_regime.py`'s dynamic weighting into
  `ChiefStrategyOfficer`'s actual department-weighting logic (the
  committee table would then reflect regime-adjusted weights, not just
  the static defaults)
- An exact pixel-for-pixel recreation of the original spec's full visual
  mockup beyond this table (see `docs/ARCHITECTURE_DASHBOARD_REDESIGN.md`
  for what was built instead and why)
