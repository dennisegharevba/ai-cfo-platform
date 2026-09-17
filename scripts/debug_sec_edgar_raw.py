"""
Diagnostic tool: dumps EVERY raw entry SEC EDGAR returns for a given
company/concept — no filtering, no bucketing, no "latest" selection.
Built specifically to investigate a real finding: running
demo_equity_crypto_agents.py twice in a row produced OPPOSITE bias
conclusions for the same company (+100.0 with EPS=6.88/Revenue=364B vs
-100.0 with EPS=2.02/Revenue=109B), both claiming the same date
(2026-06-27). The most likely explanation: SEC's raw data for that date
contains MORE THAN ONE entry (e.g. a single quarter AND a trailing-
twelve-months figure that happen to share the same "end" date but have
different "start" dates and different values) — this script prints every
one of them directly so that's visible instead of guessed at.

Run:
    python scripts/debug_sec_edgar_raw.py --cik 320193 --concept EarningsPerShareDiluted
    python scripts/debug_sec_edgar_raw.py --cik 320193 --concept Revenues
    python scripts/debug_sec_edgar_raw.py --cik 320193 --concept RevenueFromContractWithCustomerExcludingAssessedTax
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from config.settings import SEC_USER_AGENT

EDGAR_BASE_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"


def main():
    parser = argparse.ArgumentParser(description="Dump raw SEC EDGAR XBRL entries for one company/concept.")
    parser.add_argument("--cik", required=True, help="SEC CIK, e.g. 320193 for Apple")
    parser.add_argument("--concept", required=True, help="us-gaap XBRL tag, e.g. EarningsPerShareDiluted")
    args = parser.parse_args()

    if not SEC_USER_AGENT:
        print("SEC_USER_AGENT is not set — set it in .env and re-run.")
        return

    cik = str(args.cik).zfill(10)
    url = EDGAR_BASE_URL.format(cik=cik, concept=args.concept)
    headers = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

    print(f"\nFetching {url} ...\n")
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    units = data.get("units", {})
    entries = units.get("USD/shares") or units.get("USD") or []
    filed = [e for e in entries if e.get("form") in ("10-Q", "10-K") and e.get("val") is not None]
    filed.sort(key=lambda e: e.get("end", ""), reverse=True)

    print(f"Total 10-Q/10-K entries: {len(filed)}\n")
    print(f"{'end':<12} {'start':<12} {'days':>5}  {'form':<6} {'fp':<4} {'value':>20}")
    print("-" * 70)
    for e in filed[:30]:  # most recent 30 — plenty to see any same-end-date duplicates
        start, end = e.get("start"), e.get("end")
        days = None
        if start and end:
            try:
                days = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
            except ValueError:
                pass
        print(f"{end or '?':<12} {start or '?':<12} {str(days) if days is not None else '?':>5}  "
              f"{e.get('form', '?'):<6} {e.get('fp', '?'):<4} {e.get('val'):>20}")

    # Explicitly flag any end date that appears more than once — exactly
    # the scenario suspected: a quarter and a cumulative/TTM figure both
    # ending on the same date, with different start dates and values.
    end_dates_seen = {}
    for e in filed:
        end_dates_seen.setdefault(e.get("end"), []).append(e)
    duplicates = {end: es for end, es in end_dates_seen.items() if len(es) > 1}
    if duplicates:
        print(f"\n⚠ {len(duplicates)} end date(s) have MORE THAN ONE entry:")
        for end, es in duplicates.items():
            print(f"\n  end={end}:")
            for e in es:
                print(f"    start={e.get('start')}  form={e.get('form')}  fp={e.get('fp')}  val={e.get('val')}")
    else:
        print("\nNo duplicate end dates found among the most recent 30 entries.")


if __name__ == "__main__":
    main()
