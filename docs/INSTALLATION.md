# Installation Guide

## Requirements
- Python 3.11 or 3.12
- A free FRED API key (optional for this phase, but needed to see real macro
  data flow through): https://fred.stlouisfed.org/docs/api/api_key.html

## Setup

```bash
git clone <your-repo-url> ai-cfo-platform
cd ai-cfo-platform

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edit .env and paste in your FRED_API_KEY
```

## Run the dashboard

```bash
streamlit run dashboard/Home.py
```

Opens a multi-page app in your browser (Data Health, Department Reports,
Strategy Synthesis, Risk Officer, Performance & Learning, Alerts &
Execution — see docs/ARCHITECTURE_PHASE10.md). Needs the same `.env`
values as the demo scripts below to show live data.

## Run the full automated research cycle

```bash
python scripts/run_daily_cycle.py
```

Runs every asset in `config/watchlist.py` through its configured
departments, synthesizes, persists to `ai_cfo_platform.db`, and alerts via
Telegram if configured and the Chief Execution Officer's gate clears. This
is the same script GitHub Actions runs on a schedule — see
docs/ARCHITECTURE_PHASE11.md and .github/workflows/scheduled_run.yml.

## Run the Phase 1 demo

```bash
python scripts/demo_refresh.py
```

This registers three real, free data sources (FRED macro data, CFTC COT
positioning, Yahoo Finance prices) with the `DataIntegrityManager` and prints
the full fetch → validate → score → gate pipeline for each, plus the refresh
audit log.

## Run the test suite

```bash
pytest tests/ -v
```

All 22 tests use fake in-memory connectors, so they run fully offline and
deterministically — no API keys or network access required.
