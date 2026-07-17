# Architecture — Phase 2: Chief Macro Officer & Chief Bond Strategist

## The agent pattern

Every one of the twelve Chief Officers will follow this same shape — Phase 2
establishes it so Phases 3-9 are mostly "write the domain logic," not "invent
a new pattern."

```
BaseAgent.analyze(asset_or_theme)
    |
    +-- for each key in required_dataset_keys():
    |       dataset = DataIntegrityManager.get(key)
    |       if dataset.is_usable(): usable[key] = dataset
    |       else: record as a data_gap
    |
    +-- _build_report(usable, asset_or_theme)   <- subclass's domain logic,
    |                                               only ever sees usable data
    |
    +-- AgentReport (bias, bias_score, confidence, risk_level,
                      catalysts, risks, evidence, data_gaps)
```

**`agents/base_agent.py`** — `BaseAgent` is a template method: subclasses
declare *what* data they need (`required_dataset_keys()`) and *how* to turn
usable data into a report (`_build_report()`), but the fetch-and-gate step is
identical for every agent and cannot be skipped or worked around. A dataset
that fails `is_usable()` never reaches `_build_report()` — it's recorded as a
`data_gap` instead. This is the mechanism that makes the platform's "never
analyze stale/unavailable data" rule structural rather than a convention
each of the twelve agents has to remember to follow.

**`models/report.py`** — `AgentReport` is the shared output shape every
department produces (bias, bias_score -100..+100, confidence 0-100,
risk_level, catalysts, risks, evidence, data_gaps). This uniformity is what
lets the Chief Strategy Officer (Phase 7) mechanically collect reports from
every department without twelve different parsing paths.

## Chief Macro Officer (`agents/chief_macro_officer.py`)

Phase 2 scope: CPI (inflation trend) + unemployment rate (labor market
trend), combined into a single "Growth & Inflation Regime" bias score via a
50/50 weighted average of two trend components. Each component is scored
-100..+100 by `_series_trend_score()`, a small, auditable helper: percent
change from the oldest to newest observation in the fetched window,
normalized so a 5% move is treated as a "strong" signal. Confidence starts
at 40 and gains 20 per usable component (so a report built on both series
tops out at 80; a report built on only one caps at 60).

More FRED series (GDP, ISM, retail sales, etc., per the full spec's macro
list) slot into this same agent later as additional weighted components —
no architecture change needed, just more entries in `required_dataset_keys()`
and `_build_report()`.

## Chief Bond Strategist (`agents/chief_bond_strategist.py`)

Phase 2 scope: 10Y and 2Y Treasury yields. Produces a bias on **bond
prices** (not yields) since that's what's actually traded — rising yields
are bearish for bond prices, so the raw yield trend score is inverted before
becoming the report's `bias_score`. Separately, the 10Y-2Y spread is checked
for yield curve inversion: a negative spread sets `risk_level` to `HIGH` and
adds a named risk, independent of the price-bias calculation. 5Y/30Y yields
and credit spreads are the natural Phase-3-or-later additions to this same
agent.

## Why bond strategist reuses `_series_trend_score` from the macro officer

Both agents need the identical "compare oldest to newest observation in a
FRED-style history array, normalize to -100..+100" calculation. Rather than
duplicating it, the bond strategist imports it directly. If this scoring
function needs a third consumer, it should move to a shared module (e.g.
`agents/scoring_utils.py`) — two consumers is still fine to share via direct
import; a third would be the trigger to extract it.

## What's demonstrated in Phase 2

- `scripts/demo_agents.py` — registers real FRED series (CPI, UNRATE, DGS10,
  DGS2) and runs both agents end-to-end, printing full reports
- 17 new tests (39 total across the project): trend-scoring math, the
  BaseAgent data-integrity contract in isolation (via a `DummyAgent`), and
  both agents' actual bias logic under bullish/bearish/degraded-data
  scenarios — all using fake in-memory sources, so they're network-independent

As with Phase 1, this sandbox has no egress to `stlouisfed.org`, so
`demo_agents.py` here will show both agents at `confidence: 0.0`,
`risk_level: high`, with `data_gaps` listing every FRED series as `missing`
— which is the correct, intended behavior when no data source is reachable.
Once run anywhere with normal internet access and a real `FRED_API_KEY`, the
same script will produce real biases with real evidence lines. Rely on the
pytest suite for network-independent proof of the actual logic.

## What's NOT in Phase 2 (coming later)

- Ten more Chief Officers (Commodity, Equity, FX, Crypto, Sentiment,
  Technical, Risk, Strategy, Learning, Execution)
- Any persistence of reports (Chief Learning Officer, Phase 8)
- Any alerting (Chief Execution Officer, Phase 9)
- Dashboard surfacing of agent reports (Phase 10)
