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
