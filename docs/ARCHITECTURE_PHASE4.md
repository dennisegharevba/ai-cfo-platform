# Architecture — Phase 4: Chief Equity Analyst & Chief Cryptocurrency Analyst

## Extracting `trend_scoring.py` — the third-consumer trigger

Phase 2's `_series_trend_score` (in `chief_macro_officer.py`) was reused
directly by `chief_bond_strategist.py` — two consumers, fine as a direct
import per this project's own convention. Chief Equity Analyst needs the
identical "percent change from oldest to newest in a fetched window" logic
for EPS and revenue trends, which makes three consumers — the documented
trigger point for promoting it to a shared module.

`agents/trend_scoring.py` now holds:
- **`percent_change_score(values, lower_is_bullish, normalization_pct)`** —
  the pure numeric core
- **`series_trend_score(history, lower_is_bullish, normalization_pct, value_key)`**
  — extracts a named field from a newest-first list of dicts and scores it.
  `value_key` defaults to `"value"` (FRED/SEC EDGAR shape) but can be
  anything — the Chief Cryptocurrency Analyst uses `value_key="open_interest"`
  against Binance's history shape, reusing the exact same function rather
  than writing a third scoring implementation.

`chief_macro_officer.py` re-exports the old private name
(`_series_trend_score`) so nothing that already imported it — including
`chief_bond_strategist.py` and the Phase 2 tests — needed to change.

## Chief Equity Analyst (`agents/chief_equity_analyst.py`)

Same shape as the Chief Macro Officer: one instance per ticker (constructor
takes `eps_key`/`revenue_key`, mirroring how Phase 3's positioning agents
take a `cot_key`), 50/50 weighted average of two trend components, same
confidence math (40 base + 20 per usable component). Reads SEC EDGAR data
through the new `SecEdgarConnector`, which deliberately returns the same
`{"latest_value", "latest_date", "history": [...]}` shape as `FredConnector`
so it drops straight into `series_trend_score` with zero adaptation.

Per the full spec's equity coverage (buybacks, insider activity, valuation,
institutional ownership, market breadth, sector rotation), those are
straightforward additional weighted components for a later phase.

## Chief Cryptocurrency Analyst (`agents/chief_cryptocurrency_analyst.py`)

Structurally closer to Phase 3's `PositioningAgent` (one instance per
symbol, a "crowding" risk flag independent of bias direction) but crypto's
native crowding signal — perpetual funding rate — is different enough from
COT's percent-of-open-interest measure that it gets its own small module
(`agents/crypto_scoring.py`) rather than being forced into
`positioning_scoring.py`.

Two weighted components: funding rate (60%, the more direct sentiment
signal) and open interest trend (40%, confirms how much conviction is
behind the funding-rate-implied positioning). An extreme funding rate
(beyond ±0.001, i.e. ±0.1% per funding interval) is flagged as a crowded
long/short trade and elevates `risk_level` regardless of which way the bias
points — same principle as Phase 3's COT-extremity flag, different metric.

## New connectors

- **`connectors/sec_edgar_connector.py`** — free XBRL companyconcept API, no
  key, but SEC requires a descriptive `User-Agent` (see `SEC_USER_AGENT` in
  config). Filters to `10-Q`/`10-K` filings only (excludes `8-K` and other
  form types that would pollute a fundamentals trend), sorts newest-first.
- **`connectors/binance_connector.py`** — free public futures endpoints (no
  key): `openInterestHist` for the OI trend window, `premiumIndex` for the
  current funding rate. Binance returns open-interest history oldest-first;
  the connector reverses it to match this platform's newest-first
  convention (FRED, CFTC COT).

## What's demonstrated in Phase 4

- `scripts/demo_equity_crypto_agents.py` — registers real Apple Inc.
  fundamentals (CIK 320193) and real BTCUSDT futures data, runs both agents
- 35 new tests (93 total): the refactored trend-scoring module, both new
  connectors (HTTP mocked via `unittest.mock.patch`, same pattern as
  Phase 3's COT connector tests), crypto scoring math, and both agents'
  bullish/bearish/crowded/missing-data scenarios

As with every prior phase, this sandbox has no egress to `data.sec.gov` or
`fapi.binance.com`, so the demo here shows both agents at `confidence: 0.0`,
`risk_level: high` — correct behavior when sources are unreachable. Run it
anywhere with normal internet access (and a real `SEC_USER_AGENT`) for real
output.

## What's NOT in Phase 4 (coming later)

- Six more Chief Officers (Sentiment, Technical, Risk, Strategy, Learning,
  Execution)
- Buybacks/insider activity/valuation for equities; liquidation
  heatmaps/ETF flows/on-chain metrics for crypto
- Any persistence, alerting, or dashboard surfacing of these reports
