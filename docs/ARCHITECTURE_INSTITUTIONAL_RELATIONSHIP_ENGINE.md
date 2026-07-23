# Architecture — Upgrade: Institutional Relationship Engine

## What this upgrades, and why it's additive, not a rewrite

Per the upgrade spec's explicit instruction ("Do NOT replace the current
architecture"), this sits ON TOP of Phase 3's Chief Commodity/FX Analyst
blend and Phase 7's Chief Strategy Officer — nothing about how commercial
and speculative positioning are scored, or how departments are synthesized,
was thrown away. What changed is the RELATIONSHIP layer: instead of a
single ad-hoc "are commercials and speculators pulling opposite ways"
check, that relationship is now classified into three named states, and
the classification has an explicit, testable effect on confidence — never
on direction. Neither commercials nor speculators are ever treated as
"right" on their own, matching the spec's core philosophy verbatim.

## `agents/institutional_relationship.py` — the new shared module

Three independent pieces, used by two different agents:

**1. Alignment classification** (`AlignmentStatus`, `classify_alignment`,
`apply_confidence_adjustment`, `describe_alignment`) — used by
`agents/positioning_agent_base.py` (Chief Commodity/FX Analyst):

```
classify_alignment(spec_score, comm_score)
    same sign (or either ~0)          -> FULL_ALIGNMENT
    opposite signs, small magnitude   -> FULL_ALIGNMENT (not a meaningful conflict)
    opposite signs, moderate magnitude -> MILD_DIVERGENCE
    opposite signs, large magnitude   -> STRONG_DIVERGENCE
```

Each status carries a confidence adjustment (+15 / -10 / -25 percentage
points, the exact numbers from the spec), applied additively and clamped
to 0-100 by `apply_confidence_adjustment` — never zeroing out a report or
flipping its bias, only how much to trust it. `describe_alignment`
produces the evidence/risk/catalyst text `PositioningAgent` folds into its
`AgentReport`, using the spec's own vocabulary ("Institutional Alignment,"
"Institutional Divergence," "High Institutional Uncertainty").

**2. Execution readiness** (`ExecutionReadiness`, `classify_execution_readiness`)
— used by `agents/chief_strategy_officer.py`, NOT the positioning agents.
This was a deliberate placement decision: readiness depends on whether
technical confirmation exists, and only the Chief Strategy Officer sees
both the synthesized overall bias AND every individual department's own
read (including the Chief Technical Officer's) — a single positioning
agent has no visibility into what the technical desk concluded. Four
tiers, matching the spec exactly:

| Tier | Badge | Condition |
|---|---|---|
| High Conviction | 🟢 | confidence ≥70, risk ≤ moderate, AND technical confirms |
| Conditional Opportunity | 🟡 | confidence ≥50 (or high-risk-but-not-too-low-confidence) |
| Watchlist | 🔵 | some directional edge, but below Conditional's bar |
| No Trade | 🔴 | neutral bias, confidence ≤30, or high risk + low confidence |

`ChiefStrategyOfficer.synthesize()` computes `technical_confirms` by
finding the Chief Technical Officer's report among the ones it received
and checking whether its bias sign matches the overall synthesized bias
sign — `None` if no technical department contributed that cycle, `True`/
`False` if one did.

**3. Institutional commentary** (`build_institutional_commentary`) — plain
deterministic string templating, no LLM call, consistent with every other
narrative field in this platform (`trade_thesis`, `investment_committee_summary`).
It scans the synthesis's aggregated evidence/risks for an alignment-marker
line (the exact phrases `describe_alignment` produces) and leads with it
verbatim if found — the most specific, on-topic explanation available —
falling back to a generic bias/confidence framing when no positioning
department contributed that cycle (e.g. a pure-equity or pure-macro
synthesis). Closes with a readiness-appropriate sentence lifted from the
spec's own example commentary style.

## Where the new fields live

`models/strategy_report.py`'s `StrategyReport` gained two fields —
`execution_readiness: str` and `institutional_commentary: str` — both
defaulting to `""` so any existing code constructing a `StrategyReport`
without them keeps working unchanged. `database/schema.py` and
`database/report_store.py` were extended to match, INCLUDING a real
migration path (`ReportStore._migrate()`) for databases created before
this upgrade: `CREATE TABLE IF NOT EXISTS` is a no-op against a
`strategy_reports` table that already exists, so an already-running
`ai_cfo_platform.db` (a local file, or the one persisted across scheduled
GitHub Actions runs — see docs/ARCHITECTURE_PHASE11.md) would otherwise
start failing every insert with "no such column" the moment this code
shipped. `_migrate()` checks `PRAGMA table_info` and runs `ALTER TABLE ...
ADD COLUMN` only for whatever's actually missing.
`tests/test_report_store.py::test_migration_adds_new_columns_to_pre_upgrade_database`
builds a real SQLite file with the exact pre-upgrade schema and proves
`ReportStore` opens and writes to it without error.

The Strategy Synthesis dashboard page (`dashboard/pages/3_Strategy_Synthesis.py`)
now surfaces both fields, and — following the lesson from the Trade
Decision Engine integration review, where an untested render path had a
real crash bug — the render path that displays them is exercised by an
actual button click in `tests/test_dashboard_pages.py`, not just read.

## Honest scope: what the spec asked for that isn't built

The spec's Adaptive Confidence Engine and Adaptive Weighting sections ask
for the +15/-10/-25 adjustments and department weights to become dynamic,
tuned from historical testing and varying by asset class/market
regime/volatility. **This is not built.** What exists is a set of clearly
named, hand-tunable constants (`CONFIDENCE_ADJUSTMENT_PCT`,
`MILD_DIVERGENCE_MIN`, `STRONG_DIVERGENCE_MIN` in this module;
`DEFAULT_DEPARTMENT_WEIGHTS` in `chief_strategy_officer.py`, already
overridable per-instance since Phase 7) — not a live-learning system that
backtests itself and rewrites its own thresholds. Building that properly
would need a real backtesting harness against historical COT/price data,
which is a substantial project of its own, not a natural extension of
what's here. The Self-Evaluation Engine section (log every recommendation,
measure predictive accuracy, continuously recalibrate) has a real,
working foundation already in place — `agents/chief_learning_officer.py`
(Phase 8) already records every `AgentReport` and `StrategyReport` with
recorded outcomes and computes win-rate/accuracy summaries — but nothing
currently feeds those summaries back into the constants above
automatically. That closing-the-loop step is a natural next addition, not
something quietly skipped without a plan.

## What's demonstrated

- `scripts/demo_strategy_officer.py` updated to include a realistic
  "Institutional Divergence" evidence line from the Commodity Analyst,
  showing the full flow end-to-end: positioning divergence → confidence
  penalty → Execution Readiness classification → a commentary paragraph
  that actually explains why, in the spec's own voice
- 27 new tests for the relationship engine itself (alignment
  classification across all boundary cases, confidence adjustment and
  clamping, all four readiness tiers and their edge cases, commentary
  fallback behavior), 15 updated/new tests in `test_chief_strategy_officer.py`,
  1 new migration test, and 1 new dashboard interaction test — 318 tests
  total across the project, all passing, plus the existing demo scripts
  and scheduled-cycle script re-run to confirm nothing already in
  production use was disturbed
