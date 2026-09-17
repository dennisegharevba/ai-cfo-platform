"""
Run ALL available signals against ONE asset's forward returns, in a
single command — sharing one price-history fetch instead of re-fetching
it fresh per signal (21x more efficient than invoking
scripts/run_backtest.py separately for each one), and printing a single
comparison table at the end so results across every signal can be
screened side by side, the way a real quant researcher would actually
want to review many candidate factors at once rather than losing track
of results across 21 separate runs.

Run:
    python scripts/run_backtest_all.py --asset SPY
    python scripts/run_backtest_all.py --asset Gold --price-ticker GC=F
    python scripts/run_backtest_all.py --asset SPY --signals "vix,GDP,Initial Jobless Claims"

HONEST SCOPE: this can take a genuinely long time to run for real —
testing all 16 Macro factors plus VIX/Real Yield/Treasury/Fed Policy
means up to 20 separate FRED point-in-time queries PER TEST DATE, each
paced to respect FRED's rate limit (see --request-delay, and
docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md for why that pacing
exists at all). A full multi-year run at a reasonable step size is
measured in tens of minutes, not seconds — inherent to how FRED's
vintage-query API works (one request per series per date, no bulk
endpoint), not an inefficiency specific to this script. Consider
--signals to restrict to a smaller set, or a wider --step-days, if you
want a faster first pass.
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import FRED_API_KEY
from scripts.run_backtest import SIGNAL_FUNCTIONS, _resolve_price_ticker, _fetch_price_history, _needs_fred_pacing
from agents.backtest_engine import run_backtest


def main():
    parser = argparse.ArgumentParser(description="Run every available signal against one asset's forward returns.")
    parser.add_argument("--asset", required=True, help="Display name for seasonality lookup + default for price ticker resolution, e.g. 'Gold' or 'SPY'.")
    parser.add_argument("--price-ticker", default=None, help="Yahoo ticker for the price side, if it differs from --asset.")
    parser.add_argument("--signals", default="all", help="Comma-separated signal names to run, or 'all' (default) for every available signal.")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to 5 years ago")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--step-days", type=int, default=30, help="Spacing between test dates (wider than a single-signal run's default, since this multiplies across every signal)")
    parser.add_argument("--forward-days", type=int, default=20, help="Forward return window")
    parser.add_argument("--request-delay", type=float, default=0.6, help="Seconds to pause between FRED-based requests")
    args = parser.parse_args()

    signal_names = list(SIGNAL_FUNCTIONS.keys()) if args.signals == "all" else [s.strip() for s in args.signals.split(",")]
    unknown = [s for s in signal_names if s not in SIGNAL_FUNCTIONS]
    if unknown:
        print(f"Unknown signal(s): {unknown}")
        print(f"Available: {list(SIGNAL_FUNCTIONS.keys())}")
        return

    needs_fred = any(_needs_fred_pacing(s) for s in signal_names)
    if needs_fred and not FRED_API_KEY:
        print("FRED_API_KEY is not set, but at least one selected signal needs it. Set it in .env and re-run.")
        return

    price_ticker = _resolve_price_ticker(args.asset, args.price_ticker)
    print(f"\nFetching price history for {price_ticker}" +
          (f" (resolved from --asset '{args.asset}')" if price_ticker != args.asset else "") + "...")
    try:
        price_history = _fetch_price_history(price_ticker)
    except Exception as exc:
        print(f"Could not fetch price history for '{price_ticker}': {exc}")
        return
    print(f"  Got {len(price_history)} daily closes. Reused across all {len(signal_names)} signal(s) below — fetched once, not once per signal.")

    end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else end_date - timedelta(days=365 * 5)
    test_dates = []
    d = start_date
    while d <= end_date:
        test_dates.append(d)
        d += timedelta(days=args.step_days)

    results = []
    for signal_idx, signal_name in enumerate(signal_names):
        print(f"\n[{signal_idx + 1}/{len(signal_names)}] Computing '{signal_name}' for {len(test_dates)} dates...")
        signal_fn = SIGNAL_FUNCTIONS[signal_name]
        paced = _needs_fred_pacing(signal_name)
        signal_scores = []
        for i, d in enumerate(test_dates):
            score = signal_fn(d, args.asset)
            if score is not None:
                signal_scores.append((d, score))
            if paced and i < len(test_dates) - 1:
                time.sleep(args.request_delay)

        result = run_backtest(
            signal_name=signal_name, asset=args.asset, signal_scores=signal_scores,
            price_history_oldest_first=price_history, forward_window_days=args.forward_days,
        )
        results.append(result)
        print(f"  {result.sample_size} usable data points, correlation {result.correlation}")

    print(f"\n\n{'=' * 78}")
    print(f"SUMMARY — every signal vs. {args.asset}'s {args.forward_days}-day forward return")
    print("=" * 78)
    print(f"{'Signal':<35} {'N':>5} {'Correlation':>12} {'Significant?':>14} {'Overlap?':>10}")
    print("-" * 78)
    # Sort by |correlation| descending — the most promising results surface first.
    for r in sorted(results, key=lambda r: abs(r.correlation) if r.correlation is not None else -1, reverse=True):
        corr_str = f"{r.correlation:+.3f}" if r.correlation is not None else "n/a"
        sig_str = "YES" if r.likely_significant else "no" if r.likely_significant is False else "n/a"
        overlap_str = "yes" if r.windows_overlap else "no" if r.windows_overlap is False else "n/a"
        print(f"{r.signal_name:<35} {r.sample_size:>5} {corr_str:>12} {sig_str:>14} {overlap_str:>10}")

    print(f"\nFull interpretation for each signal:\n")
    for r in results:
        print(f"- {r.interpretation()}\n")


if __name__ == "__main__":
    main()
