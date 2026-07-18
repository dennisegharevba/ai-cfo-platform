# Architecture — Phase 6: Chief Risk Officer

## Why this needed a new base class, not just another BaseAgent

Every agent so far (Phases 2-5) fits `BaseAgent`'s shape: a fixed, small set
of dataset keys, gated by `is_usable()`, producing a directional read on
ONE asset or theme. The Chief Risk Officer breaks that shape in two ways:

1. **Its input is a `Portfolio`** (an arbitrary, caller-supplied list of
   positions), not a single ticker string — so it can't declare a fixed
   `required_dataset_keys()` at construction time; the keys it needs depend
   on what's IN the portfolio being analyzed.
2. **Its output isn't directional.** Per the spec, the Risk desk's job is
   to say how risky a portfolio is, not which way it's headed. Forcing a
   `bias_score` out of "portfolio volatility is 18%" would be manufacturing
   a signal that isn't there.

Rather than bend `BaseAgent` to fit, Phase 6 adds a parallel template method:
`PortfolioAgent` (`agents/portfolio_agent_base.py`). It enforces the exact
same non-negotiable rule as `BaseAgent` — never analyze a dataset that
isn't `is_usable()` — just keyed by symbol and driven by a `Portfolio`
instead of a fixed key list:

```
PortfolioAgent.analyze_portfolio(portfolio)
    |
    +-- for each position in portfolio.positions:
    |       key = price_history_key_for(position.symbol)
    |       dataset = DataIntegrityManager.get(key)
    |       if dataset.is_usable(): usable_by_symbol[symbol] = dataset
    |       else: record as a data_gap
    |
    +-- _build_report(usable_by_symbol, portfolio)   <- subclass's domain logic
    |
    +-- AgentReport (same shape every other department produces)
```

`models/portfolio.py` adds the two new dataclasses this needed:
`Position` (symbol, quantity, asset_class) and `Portfolio` (name + list of
positions) — deliberately minimal, since Phase 6 only needs enough
structure to compute market-value weights.

## Why `bias`/`bias_score` are always neutral/0.0 for this agent

`AgentReport` is the shared output shape every department uses (so the
Chief Strategy Officer, Phase 7, can collect them uniformly) — but nothing
requires every field to carry a meaningful signal for every department.
The Risk desk's actual assessment lives entirely in `risk_level` (which
IS meaningful here — LOW through HIGH) plus the `evidence`/`risks`/
`catalysts` lists. Keeping `bias_score` honestly at 0 rather than inventing
one avoids polluting whatever the Chief Strategy Officer eventually does
with department scores — a fake risk-driven "bias" would be noise, not signal.

## The five risk components (`agents/risk_calculations.py`)

Pure Python, same philosophy as `agents/technical_indicators.py` — every
formula is a textbook definition, not a library call:

- **`daily_returns`** — simple (not log) percent returns
- **`annualized_volatility`** — sample stdev of returns × √252 × 100
- **`historical_var`** — empirical percentile of the return distribution
  (linear-interpolated), not a parametric/normal-distribution assumption —
  more robust to fat tails, at the cost of needing a reasonably sized
  sample (the function returns `None` below 10 data points rather than
  producing a number that looks precise but isn't)
- **`max_drawdown`** — peak-to-trough decline over a price/index series
- **`pearson_correlation`** — standard textbook formula, aligned on the
  trailing overlap of two return series

## Combining single-asset math into a portfolio view

`ChiefRiskOfficer._build_report` does the actual portfolio-level work:

1. **Concentration** — each position's market value (`|quantity| × latest_close`)
   as a share of total portfolio value; the largest share crossing 40%/60%
   sets `risk_level` to ELEVATED/HIGH.
2. **Weighted portfolio returns** — each included symbol's daily returns,
   combined by portfolio weight into a single daily return series.
   **Documented simplification**: returns are aligned by trailing INDEX,
   not calendar date. Fine when every position trades on the same calendar
   (e.g. all US equities); wrong if mixing calendars (e.g. crypto, which
   trades every day, with equities, which don't) — a later phase should
   align by date instead.
3. **Volatility, VaR, drawdown** — all computed from that one weighted
   return series (drawdown via a reconstructed portfolio value index
   starting at 1.0).
4. **Average pairwise correlation** — across all included positions'
   individual return series; high average correlation (≥0.7) is flagged
   even though it isn't itself a loss metric, because a portfolio that
   looks diversified by asset-class labels but is highly correlated in
   practice is a real and common risk blind spot.

Every threshold (concentration, volatility, VaR, drawdown, correlation) is
a named module-level constant, not a magic number buried in a conditional —
consistent with the project's "every score/flag should be explainable in
one sentence" standard.

## No new connector

Phase 6 reuses Phase 5's `YahooHistoryConnector` across multiple symbols —
one instance per position, registered under `PRICE_HISTORY_{symbol}` keys
(same naming convention `scripts/demo_sentiment_technical_agents.py` used
for the Chief Technical Officer). No new data source was needed; this
phase is entirely about a new way of consuming existing data across many
assets at once.

## What's demonstrated in Phase 6

- `scripts/demo_risk_officer.py` — a real 4-asset portfolio (SPY, AAPL,
  GLD, TLT) run through the Chief Risk Officer
- 25 new tests (157 total): risk-calculation math against known sequences
  (concentration, correlation, drawdown edge cases), `PortfolioAgent`'s
  contract in isolation (mirroring how Phase 2 tested `BaseAgent` via a
  `DummyAgent`), and the Chief Risk Officer's concentration/correlation/
  drawdown/missing-data scenarios

As with every prior phase, this sandbox has no egress to Yahoo Finance, so
the demo here shows `confidence: 0.0`, `risk_level: high` with every
position flagged as a data gap — correct behavior when no price data is
reachable at all. Run it anywhere with normal internet access for a real
portfolio risk read.

## What's NOT in Phase 6 (coming later)

- Three more Chief Officers (Strategy, Learning, Execution)
- Date-aligned (not index-aligned) portfolio return combination
- Scenario analysis / stress testing (explicit shock scenarios), risk-adjusted
  return metrics (Sharpe/Sortino) — natural next additions to this same agent
- Any persistence, alerting, or dashboard surfacing of these reports
