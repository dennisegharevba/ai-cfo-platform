"""
FRED point-in-time (vintage) data fetching — for backtesting only.

THE PROBLEM THIS SOLVES: connectors/fred_connector.py's FredConnector
(used for all LIVE analysis) always returns the LATEST vintage of a
series — today's most-revised numbers. Many FRED series get revised
after initial publication (CPI, GDP, Retail Sales, NFP, JOLTS, Average
Hourly Earnings, Federal Debt all get revised; daily market-observed
series like the Fed Funds Rate, 10Y Treasury/TIPS yields, and VIX do NOT,
since they're prices, not survey statistics). Using today's revised CPI
to test what agents/chief_macro_officer.py would have said in, say, June
2020 is a classic look-ahead-bias mistake — the model would appear
smarter than it could actually have been, because it's being fed
information that didn't exist yet.

THE FIX: FRED's own API (the same one powering the public ALFRED archive)
accepts `realtime_start`/`realtime_end` parameters — querying with both
set to a single historical date returns the value of the series EXACTLY
AS IT WAS PUBLISHED/KNOWN on that date, not today's revision. This module
uses that parameter pair specifically for backtesting; nothing about the
live FredConnector changes.

HONEST LIMITATION: this makes ONE API call per (series, as-of-date) pair
— there's no bulk vintage-query endpoint. A broad backtest across many
series and many historical dates means many requests; agents/backtest_engine.py
paces these accordingly and this is exactly why a full historical Macro
backtest takes real time to run, not something to expect instantly.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Tuple

import requests

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Series known to be DAILY, MARKET-OBSERVED prices/rates rather than
# survey-based economic statistics — these are NEVER meaningfully revised
# after publication, so a point-in-time query for them is a courtesy
# (harmless, but not strictly necessary the way it is for CPI/GDP/NFP/etc).
# Kept here so callers/tests can document which series genuinely needed
# the vintage-query machinery vs. which didn't.
NON_REVISED_SERIES = {"DGS10", "DGS2", "DFII10", "FEDFUNDS", "VIXCLS", "DTWEXBGS", "DFEDTARU", "DFEDTARL"}


def fetch_point_in_time_value(
    series_id: str, api_key: str, as_of_date: date, timeout: int = 10,
) -> Optional[Tuple[float, date]]:
    """
    Returns (value, observation_date) for the most recent observation of
    `series_id` that was PUBLISHED/KNOWN as of `as_of_date` — never a
    later revision. Returns None (never raises) on any failure — missing
    data, a network error, an invalid series — so a backtest loop can
    simply skip that data point rather than crash or fabricate a value,
    the same "never fabricate, degrade gracefully" convention used
    throughout this platform's live connectors.
    """
    if not api_key:
        return None

    as_of_str = as_of_date.strftime("%Y-%m-%d")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": as_of_str,
        "realtime_end": as_of_str,
        "sort_order": "desc",
        "limit": 1,
        "observation_end": as_of_str,
    }
    try:
        resp = requests.get(FRED_BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    observations = data.get("observations", [])
    if not observations:
        return None

    row = observations[0]
    try:
        value = float(row["value"])
        obs_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        return value, obs_date
    except (KeyError, ValueError, TypeError):
        return None


def fetch_point_in_time_history(
    series_id: str, api_key: str, as_of_date: date, limit: int = 5, timeout: int = 10,
) -> Optional[list]:
    """
    Returns a full vintage-correct history window (newest-first list of
    {"date": ..., "value": ...} dicts) — the SAME shape
    connectors.fred_connector.FredConnector's live payload["history"]
    uses, so agents.trend_scoring.series_trend_score() can consume it
    identically whether the caller is live analysis or a backtest.

    This is what makes it possible to backtest Chief Macro Officer's
    actual factors (CPI, GDP, JOLTS, etc.) rather than just single-value
    signals: the live agent computes its trend from a 5-observation
    window (oldest vs. newest), so a historically honest backtest needs
    that SAME window, as it was known on a given historical date — not
    just the single latest point-in-time value.

    Returns None (never raises) if the query fails or returns no data.
    """
    if not api_key:
        return None

    as_of_str = as_of_date.strftime("%Y-%m-%d")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": as_of_str,
        "realtime_end": as_of_str,
        "sort_order": "desc",
        "limit": limit,
        "observation_end": as_of_str,
    }
    try:
        resp = requests.get(FRED_BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    observations = data.get("observations", [])
    if not observations:
        return None

    history = []
    for row in observations:
        if "date" in row and "value" in row:
            history.append({"date": row["date"], "value": row["value"]})
    return history if history else None
