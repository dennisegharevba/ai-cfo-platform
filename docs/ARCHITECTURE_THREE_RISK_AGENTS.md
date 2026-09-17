# The three risk agents — what each does, and why three exist

This platform has three separate classes with "risk" in the name. That's
not accidental duplication — each answers a genuinely different question,
for a different consumer, and none of them could correctly answer the
others' question. This doc exists because nothing else in the codebase
brings all three together in one place, which was a real, fair gap
identified when reviewing the platform for what could be improved.

## The three, side by side

| | `ChiefRiskOfficer` | `ChiefRiskFundamentalsOfficer` | `ChiefAssetRiskOfficer` |
|---|---|---|---|
| **File** | `agents/chief_risk_officer.py` | `agents/chief_risk_fundamentals_officer.py` | `agents/asset_risk_officer.py` |
| **Question it answers** | "How risky is my whole portfolio, right now?" | "How volatile/drawdown-prone is this ONE asset, on its own?" | "Is it currently safe to ENTER a trade in this asset?" |
| **Shape** | `PortfolioAgent` — takes a `Portfolio` of positions | `BaseAgent` — takes one ticker | `BaseAgent` — takes one ticker |
| **Built in** | Phase 6 (original platform build) | Institutional Fundamental Scoring Engine ("Risk" category) | The separate Trade Decision Engine (uploaded/integrated later) |
| **Computes** | Concentration, portfolio volatility, VaR, max drawdown, correlation across positions | Per-asset annualized volatility + max drawdown, from real Yahoo Finance price history | ATR-based stop distance, volatility, event-risk keyword detection, liquidity considerations for ENTRY timing |
| **Feeds into** | `ChiefStrategyOfficer.synthesize(risk_report=...)` | `ChiefStrategyOfficer.synthesize(risk_reports=[...])` and the Trade Decision Engine's `RISK_DEPARTMENTS` | Only the Trade Decision Engine's own Risk Score (`agents/trade_scoring.py`) |
| **Bias** | Always neutral (0) by design — a risk desk assesses HOW risky, not WHICH direction | Can be bullish/bearish-leaning (low vol = favorable), but structurally excluded from bias averaging anyway | Not directional at all — purely a go/no-go gate |

## Why not just one risk agent?

Each genuinely needs different INPUT SHAPE:

- **Portfolio-level risk (Chief Risk Officer)** is mathematically impossible
  to compute from a single asset — concentration and correlation are only
  meaningful across MULTIPLE positions. This one has to take a `Portfolio`.
- **Per-asset risk (Chief Risk Fundamentals Officer)** deliberately asks a
  narrower, single-asset question — "is THIS thing itself volatile" —
  independent of what else you hold. This is what lets it plug into the
  main per-asset research pipeline (`ChiefStrategyOfficer`) the same way
  Chief Macro Officer or Chief Commodity Fundamentals Officer do.
- **Entry-timing risk (Chief Asset Risk Officer)** answers a narrower
  question again — not "is this asset volatile in general" but "right
  now, is the SPECIFIC MOMENT of entering a trade risky" (ATR-based stop
  placement, upcoming event risk, current liquidity). This is scoped
  entirely to the separate Trade Decision Engine, which has its own
  purpose (trade entry timing) distinct from the main research pipeline's
  purpose (ongoing directional research).

Collapsing these into one class would either force a `Portfolio` object
into every single-asset call site (awkward and wasteful when all you want
is one ticker's volatility), or force per-asset callers to reason about
concentration/correlation math that doesn't apply to them.

## How they avoid confusing `ChiefStrategyOfficer`'s bias average

All risk-type signals share one design principle: "how risky" is a
different KIND of claim than "which direction," so none of them are ever
folded into the directional bullish/bearish average the way a Macro or
Sentiment reading is. `ChiefStrategyOfficer.synthesize()` has two
dedicated parameters for exactly this — `risk_report` (a single portfolio
read) and `risk_reports` (any number of others, e.g. Chief Risk
Fundamentals Officer) — both excluded from the bias-weighted average,
both still contributing `risk_level`/`risks`/`catalysts` to the final
output. See `docs/ARCHITECTURE_TRADE_DECISION_TECHNICAL_FIX.md` for the
history of how `risk_reports` (plural) came to exist, and the real bug
(a dashboard page that hadn't been updated to use it) found and fixed
along the way.

## If you're not sure which one to use

- Building a position/portfolio-level view (multiple holdings)? →
  `ChiefRiskOfficer`
- Want a real, live volatility/drawdown read on ONE asset, to feed into
  the main research pipeline for that asset? → `ChiefRiskFundamentalsOfficer`
- Deciding whether NOW is a good moment to open a specific trade? →
  the Trade Decision Engine, which uses `ChiefAssetRiskOfficer` internally
  — you don't call it directly, you call `ChiefTradeDecisionOfficer.decide()`
