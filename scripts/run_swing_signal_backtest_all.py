"""
Run the Swing Signal backtest (agents/swing_signal.py, via
agents/swing_signal_backtest.py) across EVERY FX/commodity market in
config/watchlist.py's WATCHLIST_DAILY, in a single command — both the
signal AS DESIGNED and its FADE (see scripts/run_swing_signal_backtest.py's
--fade) for each market, printing one comparison table at the end.

WHY THIS EXISTS: docs/ARCHITECTURE_SWING_SIGNAL.md's 2026-09-11 update
found a consistent losing result for the original signal and a consistent
WINNING result for the fade across the three assets tested by hand (Gold,
EUR/USD, WTI Crude Oil). Three assets is a real result, not a coincidence
sample of one, but it is still only three of the ~20 FX/commodity markets
this platform actually watches — before trusting either direction enough
to change SWING_SIGNAL_ALERTS_ENABLED, the same question needs answering
across the rest of the watchlist too. This script is that extension,
following the exact same "share what can be shared, run everything in one
command, print one comparison table" pattern scripts/run_backtest_all.py
already established for the other signals.

EFFICIENCY: for each asset, ONE COT history fetch and ONE price history
fetch are reused for BOTH the original and faded backtest (fading only
negates the already-computed scores in memory — see
scripts/run_swing_signal_backtest.py's --fade) — this halves the network
calls a naive "run the single-asset script twice per asset" approach would
make, the same reasoning run_backtest_all.py already applies to sharing
one price fetch across many signals.

One market's failure (a CFTC market name that doesn't resolve, a Yahoo
ticker that fails to fetch, insufficient signal history) is logged and
skipped, never aborts the rest of the run — the same "never let one
problem take down the whole batch" principle used throughout this
platform (scripts/run_daily_cycle.py's per-asset try/except,
agents/opportunity_screener.py, etc.).

Run:
    python scripts/run_swing_signal_backtest_all.py
    python scripts/run_swing_signal_backtest_all.py --start 2018-01-01
    python scripts/run_swing_signal_backtest_all.py --assets "Gold,Silver,EUR/USD"
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.watchlist import WATCHLIST_DAILY, COMMODITY_YAHOO_TICKERS, FX_YAHOO_TICKERS
from agents.backtest_engine import run_backtest
from agents.strategy_backtest import simulate_strategy
from agents.swing_signal_backtest import swing_signal_history
from scripts.run_backtest import _fetch_price_history
from scripts.run_swing_signal_backtest import _resolve_asset


def _all_cot_markets():
    """Every (asset display name, CFTC market name) pair from the "commodity"/
    "fx" departments in WATCHLIST_DAILY — the exact same population
    dashboard/pages/8_Swing_Signals.py's live scan covers, so this backtest
    tests the same universe the live feature actually watches."""
    return [
        (entry["asset_or_theme"], params["cot_market"])
        for entry in WATCHLIST_DAILY
        for dept, params in entry.get("departments", {}).items()
        if dept in ("commodity", "fx") and "cot_market" in params
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Run the Swing Signal backtest (original AND faded) across every FX/commodity market in the watchlist."
    )
    parser.add_argument(
        "--assets", default="all",
        help="Comma-separated asset display names (as in config/watchlist.py) to run, or 'all' (default) for every "
             "FX/commodity market with a known Yahoo ticker.",
    )
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to 5 years ago")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--window-weeks", type=int, default=8, help="Trailing COT weeks build_swing_signal() sees at each point (matches the live default)")
    parser.add_argument("--forward-days", type=int, default=20, help="Forward return / holding-period window")
    parser.add_argument("--transaction-cost-bps", type=float, default=5.0, help="Round-trip transaction cost estimate, in basis points")
    parser.add_argument("--request-delay", type=float, default=1.0, help="Courtesy pause (seconds) between markets' network calls")
    args = parser.parse_args()

    end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else end_date - timedelta(days=365 * 5)

    all_markets = _all_cot_markets()
    if args.assets != "all":
        wanted = {a.strip() for a in args.assets.split(",")}
        unknown = wanted - {a for a, _ in all_markets}
        if unknown:
            print(f"Unknown asset(s) not found in WATCHLIST_DAILY's commodity/FX entries: {sorted(unknown)}")
            print(f"Available: {sorted(a for a, _ in all_markets)}")
            return
        all_markets = [(a, m) for a, m in all_markets if a in wanted]

    print(f"\nSwing Signal batch backtest: {len(all_markets)} FX/commodity market(s), {start_date} to {end_date}")
    print(f"COT window: {args.window_weeks} weeks | Forward window: {args.forward_days} days | Round-trip cost: {args.transaction_cost_bps} bps\n")

    results = []
    skipped = []

    for i, (asset, cot_market) in enumerate(all_markets):
        print(f"[{i + 1}/{len(all_markets)}] {asset}...", end=" ", flush=True)
        _, price_ticker = _resolve_asset(asset)
        if price_ticker is None:
            print("SKIPPED (no Yahoo ticker known for this asset).")
            skipped.append((asset, "no Yahoo ticker mapping"))
            continue

        try:
            signal_scores = swing_signal_history(asset, cot_market, start_date, end_date, window_weeks=args.window_weeks)
            if not signal_scores:
                print("SKIPPED (no reversal_watch signals fired in this range).")
                skipped.append((asset, "no signals fired"))
                continue

            price_history = _fetch_price_history(price_ticker)
            if not price_history:
                print("SKIPPED (no price history returned).")
                skipped.append((asset, "no price history"))
                continue

            orig_corr = run_backtest(
                "Swing Signal", asset, signal_scores, price_history, forward_window_days=args.forward_days,
            )
            orig_strat = simulate_strategy(
                "Swing Signal", asset, signal_scores, price_history, forward_window_days=args.forward_days,
                entry_threshold=0.0, transaction_cost_bps=args.transaction_cost_bps,
            )

            faded_scores = [(d, -s) for d, s in signal_scores]
            fade_corr = run_backtest(
                "Swing Signal (FADED)", asset, faded_scores, price_history, forward_window_days=args.forward_days,
            )
            fade_strat = simulate_strategy(
                "Swing Signal (FADED)", asset, faded_scores, price_history, forward_window_days=args.forward_days,
                entry_threshold=0.0, transaction_cost_bps=args.transaction_cost_bps,
            )

            results.append({
                "asset": asset, "n": len(signal_scores),
                "orig_corr": orig_corr, "orig_strat": orig_strat,
                "fade_corr": fade_corr, "fade_strat": fade_strat,
            })
            print(f"done ({len(signal_scores)} signals).")

        except Exception as exc:  # noqa: BLE001 — one market's failure shouldn't block the rest of the batch
            print(f"FAILED ({exc}).")
            skipped.append((asset, str(exc)))

        if i < len(all_markets) - 1:
            time.sleep(args.request_delay)

    if not results:
        print("\nNo usable results — every market was skipped or failed. See above for reasons.")
        return

    def _pf(strat):
        return strat.profit_factor if strat.profit_factor is not None else float("-inf")

    print(f"\n\n{'=' * 100}")
    print(f"SUMMARY — original signal vs. its fade, across {len(results)} market(s) (sorted by faded profit factor, best first)")
    print("=" * 100)
    header = f"{'Asset':<16} {'N':>4} | {'Orig PF':>8} {'Orig Ret%':>10} {'Orig Sharpe':>12} | {'Fade PF':>8} {'Fade Ret%':>10} {'Fade Sharpe':>12} {'Fade MaxDD%':>12}"
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda r: _pf(r["fade_strat"]), reverse=True):
        os_, fs_ = r["orig_strat"], r["fade_strat"]
        orig_pf = f"{os_.profit_factor:.2f}" if os_.profit_factor is not None else "n/a"
        orig_ret = f"{os_.total_return_pct:+.1f}" if os_.total_return_pct is not None else "n/a"
        orig_sharpe = f"{os_.sharpe_ratio:.2f}" if os_.sharpe_ratio is not None else "n/a"
        fade_pf = f"{fs_.profit_factor:.2f}" if fs_.profit_factor is not None else "n/a"
        fade_ret = f"{fs_.total_return_pct:+.1f}" if fs_.total_return_pct is not None else "n/a"
        fade_sharpe = f"{fs_.sharpe_ratio:.2f}" if fs_.sharpe_ratio is not None else "n/a"
        fade_dd = f"{fs_.max_drawdown_pct:.1f}" if fs_.max_drawdown_pct is not None else "n/a"
        print(f"{r['asset']:<16} {r['n']:>4} | {orig_pf:>8} {orig_ret:>10} {orig_sharpe:>12} | {fade_pf:>8} {fade_ret:>10} {fade_sharpe:>12} {fade_dd:>12}")

    winning_fades = [r for r in results if r["fade_strat"].profit_factor is not None and r["fade_strat"].profit_factor > 1.0]
    losing_originals = [r for r in results if r["orig_strat"].profit_factor is not None and r["orig_strat"].profit_factor < 1.0]
    print(
        f"\n{len(losing_originals)}/{len(results)} market(s) show a losing ORIGINAL signal (profit factor < 1.0); "
        f"{len(winning_fades)}/{len(results)} market(s) show a winning FADED signal (profit factor > 1.0). "
        f"The three-asset hand-run in docs/ARCHITECTURE_SWING_SIGNAL.md found 3/3 and 3/3 respectively — compare "
        f"this wider run against that pattern before deciding whether the fade hypothesis holds beyond those three."
    )

    if skipped:
        print(f"\n{len(skipped)} market(s) skipped or failed:")
        for asset, reason in skipped:
            print(f"  - {asset}: {reason}")

    print(f"\nFull interpretation, market by market:\n")
    for r in results:
        print(f"--- {r['asset']} ---")
        print(f"  Original: {r['orig_strat'].interpretation()}")
        print(f"  Faded:    {r['fade_strat'].interpretation()}")
        print()


if __name__ == "__main__":
    main()
