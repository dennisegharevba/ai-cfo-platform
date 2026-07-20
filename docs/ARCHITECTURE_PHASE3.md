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

## Update (post-Phase 7): commercial positioning added alongside speculative

The original Phase 3 build scored ONLY non-commercial (speculative)
positioning. After the platform was further along (Phases 4-11 built), this
was revisited to add **commercial (producer/hedger) positioning** as a
second, blended signal — both derived from data the `CotConnector` was
already fetching (`comm_long`/`comm_short` were present in every payload
from Phase 3 onward, just unused until now).

**Why both, not a swap:** speculative and commercial positioning answer
different questions. Speculative positioning tends to be trend-following —
useful for momentum and for the existing "crowded trade" risk flag.
Commercial positioning reflects real hedging exposure against underlying
business activity, and is often read as a structural "smart money"
indicator that moves independently of (sometimes opposite to) the
speculative crowd. Replacing one with the other would have thrown away a
real signal; blending them (60% speculative / 40% commercial, the same
weighted-average pattern used everywhere else in this codebase) uses both.

**`agents/positioning_scoring.py`'s `net_position_trend_score`** was
generalized to accept `long_key`/`short_key` parameters (defaulting to
`noncomm_long`/`noncomm_short` for full backward compatibility with every
existing caller, including `ChiefSentimentOfficer`) rather than being
hardcoded to speculative fields — the same "generalize via a key parameter"
pattern `agents/trend_scoring.py`'s `value_key` already established.

**A genuinely new signal, not just an extra number:** when speculative and
commercial positioning move in opposite directions by a meaningful margin,
that divergence is flagged as an elevated risk in its own right — a
classically-watched warning that a trend may be nearing exhaustion,
independent of which way the overall bias points. `positioning_extremity_flag`
(the "crowded trade" check) deliberately stayed speculative-only: commercials
routinely run large positions as a normal consequence of hedging, so a large
commercial position isn't a crowd-risk signal the way a large speculative
one is.

6 new tests cover: commercial-only trend scoring via the generalized key
parameters, commercial and speculative trends computed independently on
the same history, agreement between the two boosting confidence to 100
(40 base + 30 per component), the divergence flag firing correctly, and
the pre-existing speculative-only behavior still working unchanged when no
commercial data is present in a payload.
