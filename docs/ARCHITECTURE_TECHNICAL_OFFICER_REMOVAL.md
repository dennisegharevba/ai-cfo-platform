# Chief Technical Officer removal — platform now scores on fundamentals + global news only

## What changed

Per explicit user request, the Chief Technical Officer department was
**fully deleted** from the platform's main scoring pipeline — code and
tests removed entirely, not just disabled. The platform's directional
research (Chief Strategy Officer's synthesis) now scores purely on
fundamentals, macro, and global news/sentiment:

- Chief Macro Officer (CPI, unemployment)
- Chief Bond Strategist (Treasury yields, yield curve)
- Chief Commodity Analyst / Chief FX Analyst (COT positioning — commercial
  + speculative, per the Institutional Relationship Engine)
- Chief Equity Analyst (SEC fundamentals — EPS, revenue)
- Chief Cryptocurrency Analyst (funding rate, open interest)
- Chief Sentiment Officer (news headline sentiment)
- Chief Risk Officer (portfolio-level, non-directional)

Chief Technical Officer's RSI/MACD/SMA-trend read is no longer part of
this list.

## What was deleted

- `agents/chief_technical_officer.py`
- `tests/test_chief_technical_officer.py`
- `scripts/demo_sentiment_technical_agents.py` (replaced by
  `scripts/demo_sentiment_agent.py`, covering Chief Sentiment Officer only)

## What was changed (not deleted)

- **`agents/chief_strategy_officer.py`** — removed the `"Chief Technical
  Officer": 0.7` entry from `DEFAULT_DEPARTMENT_WEIGHTS`, and removed the
  `technical_confirms` computation entirely (it previously scanned
  `reports` for a Chief Technical Officer entry to gate Execution
  Readiness's High Conviction tier).
- **`agents/institutional_relationship.py`** — `classify_execution_readiness()`
  dropped its `technical_confirms` parameter. High Conviction now depends
  only on confidence and risk level, not on any technical signal —
  necessarily, since no technical department exists to confirm anything
  anymore. This is a genuine behavior change, not just a code cleanup: a
  strong, confident, low-risk fundamental read can now reach High
  Conviction on its own, where previously it was capped at Conditional
  Opportunity without a technical department to confirm it.
- **`config/watchlist.py`** — removed the `"technical": {"ticker": ...}`
  entry from every equity entry in `WATCHLIST_WEEKLY`.
- **`scripts/run_daily_cycle.py`** — removed `_run_technical` and its
  `DEPARTMENT_RUNNERS["technical"]` entry, and the now-unused
  `YahooHistoryConnector`/`ChiefTechnicalOfficer` imports.
- **`dashboard/pages/2_Department_Reports.py`** — removed "Chief Technical
  Officer" from the department selector and its corresponding form block.

## What was deliberately kept unchanged: the Trade Decision Engine

The separate Institutional Trade Decision Engine (`agents/chief_trade_decision_officer.py`,
`agents/score_momentum.py`, `dashboard/pages/7_Trade_Decision_Engine.py`)
still scores Fundamental/Technical/Risk at 40/40/20 for entry timing,
**by explicit user choice** — this is a different feature (trade entry
timing for a position the user is actively considering) with a different
purpose from the main research pipeline (ongoing directional research on
an asset). Its "technical" component comes from its own
`agents/score_momentum.py`, which reads `agents/technical_indicators.py`'s
RSI/MACD/trend functions directly — it never depended on the
`ChiefTechnicalOfficer` class at all, so deleting that class doesn't
affect the Trade Decision Engine's functionality in any way. This was
verified by checking every import in `score_momentum.py`,
`trade_scoring.py`, `chief_trade_decision_officer.py`, and
`asset_risk_officer.py` before deleting anything — none of them import
`agents.chief_technical_officer`.

`agents/technical_indicators.py` itself (the shared RSI/MACD/SMA/ATR math
module) was **not** deleted, since it's still used by the Trade Decision
Engine and by `agents/risk_calculations.py`-adjacent code; only its
docstring was updated to stop pointing at the now-deleted file.

## What this means for existing recorded data

Historical `AgentReport`s already saved to `ai_cfo_platform.db` with
`department = "Chief Technical Officer"` are untouched — the database
schema didn't change, and old rows aren't deleted. They simply won't be
joined by any new ones going forward, and `ChiefLearningOfficer`'s
`department_performance_summary("Chief Technical Officer")` will keep
working and just report on however many rows already exist without
growing further.

## Testing

- 311 tests pass after this removal (down from 318 — 7 fewer since the
  dedicated `test_chief_technical_officer.py` file, covering an agent that
  no longer exists, was deleted along with the agent itself)
- Every test that referenced `classify_execution_readiness`'s old
  `technical_confirms` parameter, or used "Chief Technical Officer" as a
  test department name, was updated to match the new signature/behavior
  — not skipped or deleted wholesale
- The full test suite, the demo scripts, and `scripts/run_daily_cycle.py`
  were all re-run after these changes to confirm nothing else broke
