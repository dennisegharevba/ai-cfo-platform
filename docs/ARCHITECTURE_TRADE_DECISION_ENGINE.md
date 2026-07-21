# Architecture — Addition: Institutional Trade Decision Engine

## What this is, and how it relates to the 11-phase build

This is a substantial addition built on top of the completed 11-phase
platform, from a separate spec (an "Institutional Trade Decision Engine")
rather than the original master prompt. It runs **alongside**
`agents/chief_strategy_officer.py` and `agents/chief_execution_officer.py`,
not in place of them — same underlying `AgentReport`s, two different ways
of using them.

The core distinction from the Chief Strategy Officer: where
`ChiefStrategyOfficer.synthesize()` deliberately collapses every
department into one `overall_market_score`, `ChiefTradeDecisionOfficer.decide()`
deliberately keeps **Fundamental (40%), Technical (40%), and Risk (20%)**
scores separate and independently visible all the way through — an
execution recommendation is gated on the *relationship* between the three
(via an 8-point entry-confirmation checklist), never derived from one
blended number alone. `agents/trade_scoring.py`'s
`test_never_enters_on_overall_score_alone_when_technical_unconfirmed` is
the executable proof of that principle: a case with a strong (>65) overall
score but an unconfirmed technical read is asserted to NOT produce an
"ENTER NOW" rating.

Still never places a trade — `models/open_trade.py`'s `OpenTrade` is
explicitly a user-declared record ("I took this trade"), not something
the platform originates, matching the platform's founding principle from
Phase 1's master prompt.

## A genuine bug found and fixed during integration review

`dashboard/pages/7_Trade_Decision_Engine.py` called two helper functions
(`_fmt`, `_risk_label`) at lines 78 and 88, but they weren't defined until
lines 163 and 169 — after their use in the file's top-to-bottom execution
order. Since Streamlit executes each page script sequentially on every
rerun (function definitions aren't hoisted the way they might be in some
other languages), this raised a `NameError` and crashed the page the
moment a user clicked "Run Chief Trade Decision Officer" and results tried
to render — 100% of the time, for every user.

This was caught by actually *executing* the page with Streamlit's
`AppTest` harness (the same tool `tests/test_dashboard_pages.py` already
used for every other page, established in Phase 10 specifically because a
plain code read or a curl-based smoke test can both miss this exact class
of bug) rather than trusting the accompanying claim that "all tests pass"
— the included test suite covered the agent logic thoroughly but had no
test for the new dashboard page at all. Fixed by moving both helper
functions above their first use; `test_trade_decision_engine_full_flow_does_not_crash`
was added to `tests/test_dashboard_pages.py` specifically exercising the
run → open trade → re-run → close trade path, so this exact regression
can't reappear silently.

## What was verified before integration

- Every file claimed as "modified" (5 files) was diffed line-by-line
  against the actual current codebase and confirmed to be purely additive
  — nothing existing was changed or removed, matching what was claimed
- All 35 new tests were run against this platform's actual current code
  (not assumed to pass) — they do, bringing the total to 282
- The full existing test suite (247 tests before this addition) still
  passes unchanged
- Existing scripts (`demo_learning_officer.py`, `run_daily_cycle.py`) were
  re-run after integration to confirm the additive schema/`ReportStore`
  changes didn't disturb anything already in production use
- The one dashboard bug above was found via actual execution, not just reading

## Honest limitations (carried over from the code's own documentation, not hidden)

- **Cross-asset correlation risk** is not computed per-asset in
  `agents/asset_risk_officer.py` — that needs simultaneous multi-asset
  return series the way the portfolio-level `chief_risk_officer.py`
  already does; a single-asset agent has nothing to correlate against on
  its own. Documented in that file's docstring as a natural later addition
  once `OpenTrade` positions exist to correlate against.
- **The entry-confirmation checklist's breakout/volume/liquidity checks**
  are proxied from the existing Chief Technical Officer's MACD/SMA output
  (`agents/trade_scoring.build_entry_confirmation`), since this platform
  doesn't have explicit BOS/CHoCH or volume-profile detectors yet — a
  reasonable stand-in ("momentum confirming structure"), clearly flagged
  in that function's docstring so it's easy to swap in real detectors
  later without hunting for where the logic lives.
- **Event/news risk detection** (`agents/asset_risk_officer.py`'s
  `EVENT_RISK_KEYWORDS`) is a small curated keyword list (FOMC, CPI, NFP,
  etc.) reusing the existing `NewsRssConnector` — worth reviewing and
  extending for whatever specific assets/events matter most to you.

## Files added/changed

**New:** `models/trade_decision.py`, `models/open_trade.py`,
`agents/asset_risk_officer.py`, `agents/trade_scoring.py`,
`agents/score_momentum.py`, `agents/trade_lifecycle_officer.py`,
`agents/chief_trade_decision_officer.py`,
`dashboard/pages/7_Trade_Decision_Engine.py`, and 5 new test files.

**Additive changes:** `connectors/yahoo_history_connector.py` (added
`high`/`low` fields), `agents/technical_indicators.py` (added `atr()` and
`atr_expansion_pct()`), `database/schema.py` (added `trade_decisions` and
`open_trades` tables), `database/report_store.py` (added read/write
methods for those tables), `dashboard/dashboard_utils.py` (added badge
helpers + `get_report_store()`).
