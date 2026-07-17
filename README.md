# AI Chief Fundamental Officer Platform

An institutional-grade, multi-agent AI research platform that replicates the
workflow of an institutional trading research department — across
commodities, equities, indices, ETFs, futures, forex, bonds, and crypto.

**This is not a trading bot.** It never places trades. It produces
research, probability-based directional bias, and gated alerts (Telegram +
dashboard) for a human to act on.

Built in fully working, tested, documented phases. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) for what's done and what's next.

## Phase 1 (current): Data Integrity & Refresh Manager

The mandatory foundation every later agent depends on. No agent in this
platform is permitted to consume data that hasn't passed through it.

- Timestamps and quality-scores every dataset (0-100, fully explainable)
- Fails over to backup sources automatically
- Blocks usage of stale, unvalidated, or missing data — never fabricates
- Logs every refresh for audit
- Ships with three real, free connectors: FRED (macro), CFTC COT
  (positioning), Yahoo Finance (prices)
- 22 passing tests, CI on every push

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add your free FRED API key
python scripts/demo_refresh.py
pytest tests/ -v
```

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) and
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for details.

## Repository layout

```
core/          Data Integrity & Refresh Manager (Phase 1 — built)
connectors/    Data source adapters (FRED, CFTC COT, Yahoo — Phase 1)
config/        Settings + refresh interval defaults
tests/         22 passing tests, network-independent (fake connectors)
scripts/       demo_refresh.py — end-to-end proof
docs/          Architecture, installation, configuration, roadmap
agents/        Reserved: the 12 Chief Officers (Phase 2+)
dashboard/     Reserved: Streamlit dashboard (later phase)
telegram/      Reserved: Chief Execution Officer alerting (later phase)
database/      Reserved: Chief Learning Officer persistence (later phase)
models/        Reserved: shared schemas (later phase)
data/          Reserved: local caches/fixtures (later phase)
utils/         Shared logging setup
```
