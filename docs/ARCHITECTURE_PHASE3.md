# Architecture — Phase 3: Chief Commodity Analyst & Chief FX Analyst

## What's new: per-market agents, and a positioning-specific shared base

Phase 2's two agents (Macro, Bond) are each a *singleton* concept — there's
one US CPI, one US 10Y yield. Phase 3's two agents are different: you need
one **Chief Commodity Analyst instance per commodity** (Gold, Crude Oil,
Corn, ...) and one **Chief FX Analyst instance per currency** (EUR, JPY,
GBP, ...), because the underlying COT dataset is market-specific.

```
PositioningAgent(BaseAgent)          <- new shared base, agents/positioning_agent_base.py
    __init__(manager, cot_key, min_quality)   <- cot_key ties an instance to one market
    required_dataset_keys() -> [cot_key]
    _build_report(): reads Dataset.payload["history"], scores trend + extremity
    |
    +-- ChiefCommodityAnalyst(PositioningAgent)   department = "Chief Commodity Analyst"
    +-- ChiefFXAnalyst(PositioningAgent)          department = "Chief FX Analyst"
```

Both concrete classes are ~2 lines — all the logic lives in
`PositioningAgent`, because Phase 3's commodity and FX analysis both reduce
to "what is CFTC COT speculative positioning telling us," and duplicating
that logic across two classes would just be two copies to keep in sync.
When commodity-specific data (USDA, WASDE, EIA, weather) or FX-specific data
(rate differentials, DXY) get added in a later phase, that's the point where
`ChiefCommodityAnalyst` and `ChiefFXAnalyst` will diverge and each override
`_build_report()` with their own additional components — not before.

## Extending the COT connector for trend, not just snapshots

Phase 1's `CotConnector` fetched only the single latest weekly report — fine
for a snapshot, useless for a trend. Phase 3 extends it (same class, no
breaking change to Phase 1 callers) with a `weeks_history` parameter
(default 8) and a `history` list in the payload, mirroring the shape
`FredConnector` already used — so positioning-based agents can reuse the
"compare oldest to newest in a window" scoring pattern the macro/bond
agents established, rather than inventing a third one.

## `agents/positioning_scoring.py` — the domain logic

Two small, explainable functions:

- **`net_position_trend_score(history)`** — net speculative position
  (non-commercial long minus short) at the newest vs. oldest point in the
  fetched window, as a percent change, normalized so a 20% swing is a
  "strong" signal (wider than the macro officer's 5% band, since positioning
  data is naturally noisier week-to-week than CPI/unemployment).
- **`positioning_extremity_flag(latest_row)`** — net position as a percent
  of total open interest; beyond ±40% is flagged as a "crowded" trade
  (`crowded_long` / `crowded_short`), independent of trend direction. This
  elevates `risk_level` regardless of which way the bias points — a crowded
  long can still be *bullish* while also being *risky* (vulnerable to a
  sharp reversal), and the report reflects both facts rather than collapsing
  them into one number.

## What's demonstrated in Phase 3

- `connectors/cot_connector.py` — now fetches multi-week history; 5 new
  tests mocking the HTTP layer directly (`unittest.mock.patch`) to verify
  the parsing logic, since this is new/risky code worth testing without
  depending on CFTC's API being reachable
- `scripts/demo_commodity_fx_agents.py` — registers real Gold and Euro FX
  COT markets and runs both agents end-to-end
- 19 new tests (58 total across the project): positioning scoring math,
  both agents' bullish/bearish/crowded-positioning/missing-data scenarios,
  and a check that two instances of the same agent class with different
  `cot_key`s stay fully independent

As with prior phases, this sandbox has no egress to `publicreporting.cftc.gov`,
so the demo here shows both agents at `confidence: 0.0`, `risk_level: high` —
correct behavior when the source is unreachable. Run it anywhere with normal
internet access for real positioning-driven output.

## What's NOT in Phase 3 (coming later)

- Eight more Chief Officers (Equity, Crypto, Sentiment, Technical, Risk,
  Strategy, Learning, Execution)
- USDA/WASDE/EIA/weather connectors (commodity-specific fundamentals)
- Rate differential / DXY logic (FX-specific fundamentals)
- Any persistence, alerting, or dashboard surfacing of these reports
