# AI Chief Fundamental Officer Platform

An institutional-grade, multi-agent AI research platform that replicates the
workflow of an institutional trading research department — across
commodities, equities, indices, ETFs, futures, forex, bonds, and crypto.

**This is not a trading bot.** It never places trades. It produces
research, probability-based directional bias, and gated alerts (Telegram +
dashboard) for a human to act on.

Built in fully working, tested, documented phases. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) for what's done and what's next.

## Phase 1: Data Integrity & Refresh Manager

The mandatory foundation every later agent depends on. No agent in this
platform is permitted to consume data that hasn't passed through it.

- Timestamps and quality-scores every dataset (0-100, fully explainable)
- Fails over to backup sources automatically
- Blocks usage of stale, unvalidated, or missing data — never fabricates
- Logs every refresh for audit
- Ships with three real, free connectors: FRED (macro), CFTC COT
  (positioning), Yahoo Finance (prices)

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Phase 2 (current): Chief Macro Officer + Chief Bond Strategist

The first two analytical agents, and the template every remaining Chief
Officer will follow.

- `BaseAgent` structurally enforces the data-integrity rule: an agent can
  never see a dataset that failed `is_usable()` — it's recorded as a
  `data_gap` and excluded before the agent's own logic ever runs
- Shared `AgentReport` output model (bias, confidence, risk, catalysts,
  risks, evidence, data_gaps) — every future officer reports in this same shape
- Chief Macro Officer: CPI + unemployment trend → growth/inflation regime bias
- Chief Bond Strategist: 10Y/2Y yield trend → bond price bias, plus yield
  curve inversion risk flagging

See [`docs/ARCHITECTURE_PHASE2.md`](docs/ARCHITECTURE_PHASE2.md) for the full design.

## Phase 3 (current): Chief Commodity Analyst + Chief FX Analyst

Per-market positioning agents, built on a new shared `PositioningAgent` base.

- One agent instance per market (e.g. `ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")`)
  — each is tied to a specific CFTC COT dataset key
- `CotConnector` extended to fetch multi-week positioning history (not just
  the latest snapshot), so agents can score positioning *trend*
- Flags "crowded" long/short positioning (>40% of open interest) as an
  elevated-risk signal, independent of the directional bias itself
- Chief Commodity Analyst and Chief FX Analyst are currently ~2 lines each —
  all shared logic lives in `PositioningAgent`; they'll diverge once
  commodity-specific (USDA/EIA/weather) and FX-specific (rate differentials,
  DXY) data get added in later phases

See [`docs/ARCHITECTURE_PHASE3.md`](docs/ARCHITECTURE_PHASE3.md) for the full design.

## Phase 4 (current): Chief Equity Analyst + Chief Cryptocurrency Analyst

- Chief Equity Analyst: EPS + revenue trend per ticker, via a new free SEC
  EDGAR connector (10-Q/10-K filings only, no API key — just a descriptive
  User-Agent)
- Chief Cryptocurrency Analyst: funding rate (60%) + open interest trend
  (40%) per symbol, via a new free Binance futures connector; flags extreme
  funding rates as a crowded long/short trade
- Extracted `agents/trend_scoring.py` as a shared module once a third agent
  needed the same "trend from a fetched window" scoring logic

See [`docs/ARCHITECTURE_PHASE4.md`](docs/ARCHITECTURE_PHASE4.md) for the full design.

**93 passing tests total, CI on every push.**

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add your free FRED API key + SEC_USER_AGENT
python scripts/demo_refresh.py
python scripts/demo_agents.py
python scripts/demo_commodity_fx_agents.py
python scripts/demo_equity_crypto_agents.py
pytest tests/ -v
```

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) and
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for details.

## Repository layout

```
core/          Data Integrity & Refresh Manager (Phase 1 — built)
connectors/    FRED, CFTC COT, Yahoo, SEC EDGAR, Binance (Phases 1, 3 & 4)
agents/        BaseAgent + all 6 Chief Officers built so far (Phases 2-4)
models/        Shared AgentReport model (Phase 2 — built)
config/        Settings + refresh interval defaults
tests/         93 passing tests, network-independent (fake sources, mocked HTTP)
scripts/       demo_refresh.py, demo_agents.py, demo_commodity_fx_agents.py,
               demo_equity_crypto_agents.py
docs/          Architecture (Phases 1-4), installation, configuration, roadmap
dashboard/     Reserved: Streamlit dashboard (later phase)
telegram/      Reserved: Chief Execution Officer alerting (later phase)
database/      Reserved: Chief Learning Officer persistence (later phase)
data/          Reserved: local caches/fixtures (later phase)
utils/         Shared logging setup
```
