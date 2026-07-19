# Architecture — Phase 7: Chief Strategy Officer

## A third architectural shape

- **`BaseAgent`** (Phases 2-5): fetches a fixed set of dataset keys via
  `DataIntegrityManager`, analyzes one asset/theme.
- **`PortfolioAgent`** (Phase 6): fetches one dataset per position in a
  caller-supplied `Portfolio`, analyzes the portfolio as a whole.
- **`ChiefStrategyOfficer`** (Phase 7): fetches **nothing**. It has no
  `DataIntegrityManager` dependency at all — its only input is a list of
  `AgentReport`s that other agents already produced. This is intentional:
  the Strategy Officer's job per the spec is to sit *above* every
  department, collecting their already-finished analysis, not to go do its
  own data collection. Giving it a `DataIntegrityManager` would have been
  giving it a responsibility that isn't its job.

This is also the first agent whose payoff genuinely shows up only when
departments **disagree** — every prior single-department demo either shows
a real bias (with network access) or a correctly-blocked "no data"
result. This one's demo (`scripts/demo_strategy_officer.py`) deliberately
constructs a mixed scenario — bullish fundamentals, a cautious technical
read, elevated portfolio risk — using illustrative example reports rather
than live data, since illustrating *this* agent's actual value (conflict
resolution) doesn't depend on network access the way every earlier agent's
did.

## Weighting and the disagreement penalty

Each report's influence on the final synthesis is:

```
effective_weight = department_weight × (report.confidence / 100)
```

`department_weight` defaults to 1.0 for every department except Chief
Sentiment Officer and Chief Technical Officer (0.7 each) — a common
institutional convention of treating fundamentals as the primary driver and
sentiment/technicals as confirming/timing signals. Fully configurable per
instance (`ChiefStrategyOfficer(department_weights={...})`).

A report with `confidence == 0` (the pattern every prior agent uses when it
had zero usable data) automatically drops to `effective_weight == 0` and is
excluded — no special-casing needed; the same "confidence honestly reflects
data availability" design from every earlier phase does the exclusion work
for free here too.

**Resolving disagreement** (the spec's explicit requirement) is done with a
weighted standard deviation of the contributing departments' `bias_score`s:

```
overall_bias_score  = weighted_mean(bias_scores, weights)
disagreement        = weighted_stdev(bias_scores, weights)
confidence_score     = weighted_mean(confidences, weights) − min(40, disagreement × 0.4)
```

High agreement (departments clustered near the same score) leaves
confidence close to the raw weighted average. High disagreement (bulls and
bears roughly balanced) both pulls `overall_bias_score` toward neutral (via
the weighted mean itself) AND separately docks up to 40 confidence points —
because a synthesized score sitting at "neutral" for two completely
different reasons (genuine consensus that nothing's happening, vs. a
coin-flip between strongly-held opposing views) should NOT be reported with
the same confidence. This is the concrete mechanism behind "resolves
disagreements" rather than just averaging and hoping.

## Why the Chief Risk Officer is handled specially

`risk_report` is a separate, optional parameter to `synthesize()`, not just
another entry in the `reports` list — deliberately, because:

- Its `bias_score` is always 0 by design (Phase 6: the Risk desk doesn't
  take a directional view). Dumping it into the same weighted-average pool
  as directional reports would silently drag every synthesis toward
  neutral in proportion to how confident the Risk Officer was in ITS
  (non-directional) assessment — a bug that would be easy to introduce and
  hard to notice, since it fails "quietly" (a bit more neutral bias) rather
  than loudly.
- Its `risk_level` and `risks`/`catalysts` DO matter to the final output —
  a real investment committee needs to hear "portfolio volatility is
  elevated" even when every directional department is bullish. So it feeds
  into `risk_level` escalation (via the shared `worst_of()` — see below)
  and the aggregated risks list, just not the bias math.

## Extracting `agents/risk_severity.py`

Phase 6's `_worse()`/`_SEVERITY_ORDER` (a private helper for combining
several `RiskLevel` readings into one worst-case verdict) now has a second
consumer here, so it moved to a shared module — same
third-consumer-eventually-but-here-it-was-the-second-consumer-and-still-
worth-sharing reasoning as `agents/trend_scoring.py` in Phase 4.
`chief_risk_officer.py` was updated to import `worse_risk_level` from there
(aliased back to its old local name `_worse` so none of its own code needed
to change) rather than maintaining two copies of the same ordering logic.

## Trade thesis and investment committee summary

Both are built with plain string templating — no LLM call, no external
dependency — consistent with the rest of the platform's preference for
deterministic, testable, explainable output over generated prose. The
trade thesis is one sentence (bias, score, confidence, how many departments
contributed, and an agreement/disagreement note); the committee summary is
a few sentences covering the same ground plus which departments were
excluded and the top 3 catalysts/risks.

## Invalidation notes — a documented simplification

The spec asks for "invalidation levels," which implies concrete price
levels (e.g. "invalidated below $X support"). Phase 7 doesn't have the
infrastructure for that yet — no department currently computes support/
resistance levels — so `invalidation_notes` is deliberately qualitative:
the top 3 aggregated risk flags, reframed as "Thesis is weakened if: ...".
This is honest about being a placeholder rather than pretending to a
precision the platform doesn't have yet. A natural later addition: extend
the Chief Technical Officer with support/resistance detection and have
this agent reference those specific levels instead.

## What's demonstrated in Phase 7

- `scripts/demo_strategy_officer.py` — a deliberately mixed scenario
  (bullish fundamentals, cautious technicals, elevated risk) run through
  the full synthesis, showing a moderate-confidence bullish call with real
  disagreement penalties applied — output is fully reproducible without
  network access, unlike every prior phase's demo
- 14 new tests (171 total): the shared risk-severity helpers, and the
  Chief Strategy Officer's consensus/conflict/exclusion/weighting/
  risk-report-handling/empty-input scenarios

## What's NOT in Phase 7 (coming later)

- Two more Chief Officers (Learning, Execution)
- Concrete price-level invalidation (needs support/resistance detection)
- Any persistence of these synthesized reports (Chief Learning Officer,
  Phase 8) or alerting on them (Chief Execution Officer, Phase 9)
