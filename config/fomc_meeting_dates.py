"""
FOMC_MEETING_DATES: the actual, real FOMC meeting schedule dates —
EXPLICITLY user-maintained, not fabricated.

Why this ships empty rather than pre-filled: the Fed publishes its meeting
schedule up to ~2 years ahead on its own site, but exact dates are
sometimes adjusted, and this codebase has no live connector for it. Rather
than guess or reconstruct specific calendar dates from training data (this
platform's standing rule — see every other "best-effort, verify yourself"
data file, e.g. config/cftc_markets.py, config/sp500_tickers.py — is to
never present an unverified guess as fact), this list ships EMPTY. With no
dates configured, agents.market_regime.classify_regime simply never
detects an FOMC week, which is the correct, honest behavior for
unconfigured data (same principle as core.dataset.Dataset.is_usable()
blocking on missing data throughout this whole platform) — never silently
wrong, just visibly incomplete until you fill it in.

To populate this with the real schedule:
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm — copy the
scheduled meeting dates (the announcement day of each two-day meeting,
which is what matters for market positioning) into the list below.

Example format (uncomment and edit with REAL dates from the Fed's site):
    FOMC_MEETING_DATES = [
        date(2026, 1, 28),
        date(2026, 3, 18),
        # ...
    ]
"""

from datetime import date
from typing import List

FOMC_MEETING_DATES: List[date] = []
