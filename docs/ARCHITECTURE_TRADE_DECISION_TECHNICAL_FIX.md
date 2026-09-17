# Four real bugs found and fixed: Strategy Synthesis + Trade Decision Engine

## How these were found

Not from routine testing — from a direct user question ("does the trade
decision engine & strategy synthesis draw their final conclusions from
[commodity fundamentals] and Chief Risk Fundamentals Officer
respectively?"). Rather than answer from memory, the actual code was
read end-to-end for both features, which surfaced four genuine,
previously-unnoticed gaps — all now fixed and tested.

## Bug 1: Strategy Synthesis dashboard never used the risk_reports split

`agents/chief_strategy_officer.py` gained a `risk_reports` parameter
specifically so a "how risky" claim (e.g. Chief Risk Fundamentals
Officer's volatility/drawdown read) never gets folded into the
directional bullish/bearish average — only `scripts/run_daily_cycle.py`
was ever actually updated to use it. `dashboard/pages/3_Strategy_Synthesis.py`
still passed every matching report into the single directional
`reports` parameter:

```python
result = officer.synthesize(asset, matching)   # BEFORE: undifferentiated
```

This meant a genuine, correctly-computed "low volatility" reading from
Chief Risk Fundamentals Officer could silently pull the overall bias
bullish, exactly the outcome the `risk_reports` parameter exists to
prevent. Fixed by splitting `matching` into directional and risk-type
reports before calling `synthesize()`, using the same department-name
set (`{"Chief Risk Officer", "Chief Risk Fundamentals Officer"}`) the
correctly-working `run_daily_cycle.py` already implicitly uses.
`test_strategy_synthesis_correctly_excludes_risk_reports_from_bias`
proves this directly: a bullish Macro report + a bearish-scored Risk
Fundamentals report for the same asset now correctly stays bullish,
with risk_level still escalated.

## Bug 2 & 3: Trade Decision Engine silently excluded newer departments

`agents/trade_scoring.py`'s `FUNDAMENTAL_DEPARTMENTS` and
`RISK_DEPARTMENTS` sets were built before the Institutional Fundamental
Scoring Engine's newer categories existed, and were never revisited when
those categories were added:

- **Chief Commodity Fundamentals Officer** (real gold/commodity
  fundamentals — real yields, dollar index, Fed funds rate) was missing
  from `FUNDAMENTAL_DEPARTMENTS` entirely — directly relevant since this
  is exactly the department that carries gold/commodity fundamentals into
  this engine.
- **Chief Seasonality Officer** was also missing.
- **Chief Risk Fundamentals Officer** was missing from `RISK_DEPARTMENTS`
  — its real, computed volatility/drawdown data was invisible to this
  engine's Risk Score even when present in the reports passed to `decide()`.

All three now added. Chief Macro Officer and Chief Equity Analyst were
already present — `test_fundamental_score_still_includes_macro_and_equity`
proves this directly, since these were the departments specifically
named as ones to prioritize.

## Bug 4: Technical Score has been permanently stuck at neutral since Chief Technical Officer was removed

The most significant finding. `decide()` determined its technical input
by searching for a report literally named `"Chief Technical Officer"`:

```python
technical_report = next((r for r in reports if r.department == trade_scoring.TECHNICAL_DEPARTMENT), None)
```

That department was fully deleted from the platform's main pipeline in
an earlier delivery (per explicit user request — see
`docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md`). No report can ever be
named that again. This document's own earlier claim — that the Trade
Decision Engine's technical logic "never depended on [Chief Technical
Officer]'s code in the first place" — was technically true about imports
but mischaracterized the actual runtime behavior: `decide()` DID depend
on a report by that exact NAME existing, which became permanently
impossible the moment that department was removed. Every run of the
Trade Decision Engine through the dashboard since then has had its
Technical Score (40% of the overall blend) silently stuck at the neutral
50.0 default — a real regression, not by design, undiscovered until this
review.

### The fix: real technical scoring computed fresh from price history

`agents/trade_scoring.py` gained two new pieces, reusing this platform's
existing, tested indicator math (`agents/technical_indicators.py`) rather
than resurrecting any deleted code:

- **`technical_score_from_price_history(history)`** — RSI(14) 20% + MACD
  histogram 40% + SMA(20/50) trend 40%, the same weighting this
  platform's documentation has always cited for technical scoring,
  rebuilt fresh. Returns the honest neutral default with an explicit
  exclusion note when there isn't enough history — never a fabricated
  partial read.
- **`build_synthetic_technical_report(history)`** — `build_entry_confirmation()`
  reads evidence/catalyst TEXT (a documented simplification from when the
  Trade Decision Engine was first built — see that function's own
  docstring), not structured fields, so a synthetic `AgentReport` is
  built with genuinely truthful descriptions of what RSI/MACD/SMA
  actually show ("an uptrend," "accelerating higher," etc.) — these
  phrases weren't reverse-engineered from the checker's vocabulary; they
  happen to match because that's genuinely how these readings are
  normally described.

`ChiefTradeDecisionOfficer.decide()` gained an optional `price_history`
parameter. When supplied, both pieces above are used for a real Technical
Score; when omitted, `decide()` falls back to the exact old
(permanently-neutral) behavior, for backward compatibility with anything
still constructing a fake "Chief Technical Officer" report directly.

`dashboard/pages/7_Trade_Decision_Engine.py` now has its own ticker input
— separate from the department-report ticker inputs elsewhere — which
fetches real Yahoo Finance price history (reusing the same
`PRICE_HISTORY_<TICKER>` key convention Chief Risk Fundamentals Officer
already uses) and passes it through. Left blank, the page still works
exactly as before (neutral Technical Score default), never a crash.

## Testing

- 1 new dashboard regression test for Bug 1, with real conflicting
  bullish/bearish data proving the fix
- 5 new `trade_scoring.py` tests directly proving Chief Commodity
  Fundamentals Officer, Chief Seasonality Officer, and Chief Risk
  Fundamentals Officer are now included, plus that Macro/Equity remain
  included
- 11 new tests for the real technical scoring (`technical_score_from_price_history`,
  `build_synthetic_technical_report`) covering bullish/bearish/empty/
  insufficient-data/malformed-row cases and direct proof the synthetic
  report's evidence text genuinely drives `build_entry_confirmation`
- 3 new tests in `ChiefTradeDecisionOfficer`'s own suite proving
  `decide()` uses the real score when `price_history` is supplied and
  falls back correctly when it isn't
- 1 new dashboard test specifically entering a ticker into the Trade
  Decision Engine page (the prior test never touched this field)
- 513 tests total, all passing, zero regression to any existing behavior
