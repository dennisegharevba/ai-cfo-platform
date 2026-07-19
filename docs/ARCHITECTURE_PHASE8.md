# Architecture — Phase 8: Chief Learning Officer

## A fourth architectural shape

- **`BaseAgent`/`PortfolioAgent`** (Phases 2-6): produce a fresh `AgentReport`
  from live data fetched via `DataIntegrityManager`.
- **`ChiefStrategyOfficer`** (Phase 7): fetches no data — pure synthesis
  over other agents' `AgentReport`s into a `StrategyReport`.
- **`ChiefLearningOfficer`** (Phase 8): produces **neither**. It has no
  `analyze()` method at all — it's a persistence sink other agents write
  their finished reports into, and a query engine for performance analytics
  over everything that's accumulated. This is the platform's memory, not
  another opinion-former.

## Why SQLite, and why one connection held open

`database/report_store.py`'s `ReportStore` uses Python's standard-library
`sqlite3` — free, zero-config, no server to run, consistent with every
other "free or already-justified" tooling choice in this platform.

The store holds **one connection open for its whole lifetime** rather than
reconnecting per call. This matters specifically for `:memory:` databases
(used throughout the test suite and the Phase 8 demo): SQLite's in-memory
databases are scoped to the connection that created them, so reconnecting
per call would silently lose every row between calls. `check_same_thread=False`
is set up front in anticipation of Phase 10's Streamlit dashboard, which
will run across multiple request threads — safe for now since the platform
has no concurrent-write hot path yet, but worth flagging as a decision made
ahead of its immediate need.

## Schema (`database/schema.py`)

Three tables, matching the spec's "store every report, every alert, every
trade thesis, confidence score, outcome":

- **`agent_reports`** — one row per `AgentReport` any department ever produced
- **`strategy_reports`** — one row per `ChiefStrategyOfficer.synthesize()` call
- **`outcomes`** — realized results, linked to a `strategy_report_id`,
  recorded separately and later (see below)

List-valued fields (catalysts, risks, evidence, etc.) are stored as JSON
text rather than normalized child tables — SQLite has no native array
type, and a child table for what's fundamentally a list of short strings
would add real complexity for no analytical benefit at this stage.

## Outcomes are judged, not computed

`record_outcome(strategy_report_id, realized_return_pct, was_correct, notes)`
is a deliberately manual, separate step from synthesis. This platform never
places trades (see the top-level README) — there is no order fill to check
against. "Was this thesis correct" is a judgment call about whether reality
subsequently moved the way the synthesized bias said it would, made by
whoever reviews the thesis later (a person, or a future automated check
against realized price data — not built in Phase 8). `strategy_accuracy_summary()`
deliberately **excludes** strategy reports with no recorded outcome yet from
its win-rate calculation, rather than treating "not yet judged" as a loss —
an unreviewed thesis isn't a wrong one, and conflating the two would make
the win rate meaningless for any thesis still in flight.

## `ChiefLearningOfficer`'s two analytics methods

- **`department_performance_summary(department)`** — report count, average
  confidence, bias distribution (how often each department has called
  bullish/bearish/neutral historically), and what fraction of its reports
  were degraded (had `data_gaps`) — a direct measure of how often a
  department has actually been working with full information.
- **`strategy_accuracy_summary(asset_or_theme)`** — win rate and average
  realized return across every JUDGED strategy report for that asset
  (or across everything, if no asset is given).

Both are computed with plain Python aggregation over rows already fetched
from SQLite (not raw SQL `GROUP BY`/`AVG`) — the row counts this platform
deals with (hundreds to low thousands of reports between dashboard
refreshes, not millions) don't need query-level aggregation yet, and
keeping the math in Python keeps it as inspectable as every other scoring
function in this codebase.

## What's demonstrated in Phase 8

- `scripts/demo_learning_officer.py` — three illustrative research cycles
  for Gold (mirroring Phase 7's demo style), each recorded through the
  Learning Officer, synthesized, and given a recorded outcome, followed by
  real department and asset-level performance summaries pulled back out
- 19 new tests (190 total): `ReportStore`'s save/query/filter/limit
  behavior directly against SQLite, and `ChiefLearningOfficer`'s analytics
  methods against seeded historical data (including the "unjudged outcomes
  don't count as losses" behavior)

## What's NOT in Phase 8 (coming later)

- One remaining Chief Officer: Chief Execution Officer (Phase 9)
- Automated outcome judging against realized market data (currently
  manual/external)
- Any dashboard surfacing of this history (Phase 10) — though
  `department_performance_summary`/`strategy_accuracy_summary` are already
  shaped to be dropped straight into a Streamlit table or chart
- Using this recorded history to actually adjust future department weights
  or scoring (the spec's "to improve future scoring") — Phase 8 stores and
  reports the data that would inform that; actually feeding it back into
  `ChiefStrategyOfficer`'s department weights is a natural next step once
  there's enough real history to learn from
