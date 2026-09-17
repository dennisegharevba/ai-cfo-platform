"""
Backtest the Swing Signal feature (agents/swing_signal.py) for real: does a
historical COT reversal-against-trend actually precede a favorable forward
price move, and would trading every one of them historically have made
money?

Runs BOTH of this platform's two backtest engines on the exact same
signal history (agents/swing_signal_backtest.py's swing_signal_history()):

    - agents.backtest_engine.run_backtest() — correlation validation
      ("does the signal's sign/magnitude line up with subsequent returns?")
    - agents.strategy_backtest.simulate_strategy() — simulated trades
      (win rate, profit factor, Sharpe/Sortino, max drawdown), i.e. "if
      you'd actually traded every fired signal, what would have happened?"

HONEST LIMITATION (see agents/swing_signal_backtest.py's own docstring for
the full account): every backtested signal here is COT-only — no
historical news sentiment exists to cross-check against (this platform's
RSS news connector has no headline archive). This answers a narrower
question than the live feature: does the COT-reversal mechanism alone
have predictive value? If it doesn't, the live feature's news cross-check
can't be assumed to be what rescues it, since news was never validated
here either.

Needs real network access (CFTC's public COT endpoint + Yahoo Finance for
price history) — cannot produce a real answer from a sandbox with no
network access. Every date this script can't get real COT or price data
for is skipped, not estimated, so a partial-network run just shows a
smaller (honestly labeled) sample size, never a fabricated one.

Run:
    python scripts/run_swing_signal_backtest.py --asset Gold
    python scripts/run_swing_signal_backtest.py --asset "EUR/USD" --start 2018-01-01
    python scripts/run_swing_signal_backtest.py --asset "WTI Crude Oil" --forward-days 10 --window-weeks 6

FADE HYPOTHESIS (--fade): the 2026-09-11 run of this script against three
assets (Gold, EUR/USD, WTI Crude Oil) found a consistent NEGATIVE
correlation with forward returns and a losing strategy (profit factor < 1)
on all three — see docs/ARCHITECTURE_SWING_SIGNAL.md's "Backtesting"
section. That raised a specific, testable hypothesis: a single-week
pullback in COT positioning off an extreme reading may more often be a
PAUSE within the original trend (which then resumes) than a genuine
reversal — i.e. the signal's direction may be backwards more often than
not, not merely uninformative. --fade tests exactly that: it inverts every
fired signal's direction (BULLISH_TURN <-> BEARISH_TURN) before scoring,
so a "long" trade becomes "short" and vice versa, then runs the same two
backtest engines on the inverted series. This reuses build_swing_signal()
and both backtest engines completely unmodified — only the sign of the
already-computed scores is flipped at the call site here, nothing about
how a signal is detected or scored changes.

    python scripts/run_swing_signal_backtest.py --asset Gold --fade
    python scripts/run_swing_signal_backtest.py --asset "EUR/USD" --fade
    python scripts/run_swing_signal_backtest.py --asset "WTI Crude Oil" --fade

--asset must match a display name already in config/watchlist.py's
WATCHLIST_DAILY (commodity or FX entries only — Swing Signal is scoped to
the same FX/commodity watchlist the live feature covers). Its CFTC market
name and Yahoo price ticker are resolved automatically from there; use
--cot-market / --price-ticker to override either explicitly.
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.watchlist import WATCHLIST_DAILY, COMMODITY_YAHOO_TICKERS, FX_YAHOO_TICKERS
from agents.backtest_engine import run_backtest
from agents.strategy_backtest import simulate_strategy
from agents.swing_signal_backtest import swing_signal_history
from scripts.run_backtest import _fetch_price_history


def _resolve_asset(asset: str, explicit_cot_market: str = None, explicit_price_ticker: str = None):
    """
    Looks `asset` up in WATCHLIST_DAILY's commodity/fx entries for its CFTC
    market name and Yahoo price ticker — the same resolution
    dashboard/pages/8_Swing_Signals.py already does for the live feature,
    so this backtest tests the exact same markets the live scan covers.
    Explicit --cot-market/--price-ticker always win, for an asset not in
    the watchlist or a ticker mapping this platform doesn't have yet.
    """
    cot_market = explicit_cot_market
    if cot_market is None:
        for entry in WATCHLIST_DAILY:
            if entry["asset_or_theme"] != asset:
                continue
            for dept, params in entry.get("departments", {}).items():
                if dept in ("commodity", "fx") and "cot_market" in params:
                    cot_market = params["cot_market"]
                    break

    price_ticker = explicit_price_ticker
    if price_ticker is None:
        price_ticker = COMMODITY_YAHOO_TICKERS.get(asset) or FX_YAHOO_TICKERS.get(asset)

    return cot_market, price_ticker


def main():
    parser = argparse.ArgumentParser(description="Backtest agents.swing_signal against real historical COT + price data.")
    parser.add_argument("--asset", required=True, help="Display name from config/watchlist.py, e.g. 'Gold', 'EUR/USD'")
    parser.add_argument("--cot-market", default=None, help="Override: exact CFTC market_and_exchange_name")
    parser.add_argument("--price-ticker", default=None, help="Override: Yahoo Finance ticker for price returns")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to 5 years ago")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--window-weeks", type=int, default=8, help="Trailing COT weeks build_swing_signal() sees at each point (matches the live default)")
    parser.add_argument("--forward-days", type=int, default=20, help="Forward return / holding-period window")
    parser.add_argument("--transaction-cost-bps", type=float, default=5.0, help="Round-trip transaction cost estimate for the trade simulation, in basis points")
    parser.add_argument(
        "--fade", action="store_true",
        help="Test the FADE hypothesis: invert every fired signal's direction before scoring "
             "(long<->short), instead of trading it as originally detected. See this script's "
             "module docstring for why.",
    )
    args = parser.parse_args()

    cot_market, price_ticker = _resolve_asset(args.asset, args.cot_market, args.price_ticker)
    if cot_market is None:
        print(f"Could not resolve a CFTC market for '{args.asset}' from config/watchlist.py's commodity/FX "
              f"entries. Pass --cot-market explicitly (the exact market_and_exchange_names string, e.g. "
              f"'GOLD - COMMODITY EXCHANGE INC.').")
        return
    if price_ticker is None:
        print(f"Could not resolve a Yahoo Finance ticker for '{args.asset}'. Pass --price-ticker explicitly.")
        return

    end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else end_date - timedelta(days=365 * 5)

    print(f"\nSwing Signal backtest for '{args.asset}'")
    print(f"  CFTC market:  {cot_market}")
    print(f"  Price ticker: {price_ticker}")
    print(f"  Date range:   {start_date} to {end_date}")
    print(f"  COT window:   {args.window_weeks} weeks (matches the live feature's default)")
    print(f"\n  HONEST LIMITATION: this backtest is COT-only — no historical news sentiment exists to")
    print(f"  cross-check against, so every signal here is scored as if news were unavailable (the live")
    print(f"  feature's NO_DATA case: base confidence, no news bonus/penalty). See")
    print(f"  agents/swing_signal_backtest.py's docstring for the full account.\n")

    print("Fetching COT history and computing Swing Signal fires...")
    signal_scores = swing_signal_history(args.asset, cot_market, start_date, end_date, window_weeks=args.window_weeks)
    print(f"  {len(signal_scores)} Swing Signal(s) fired in this date range.")
    if not signal_scores:
        print("\nNothing to backtest — no reversal_watch signals fired for this asset/date range. "
              "Try a wider date range, or confirm --cot-market is correct.")
        return

    signal_label = "Swing Signal"
    if args.fade:
        signal_scores = [(d, -score) for d, score in signal_scores]
        signal_label = "Swing Signal (FADED -- direction inverted)"
        print(
            "\n  FADE MODE: every fired signal's direction has been inverted (BULLISH_TURN <-> "
            "BEARISH_TURN) before scoring -- testing whether trading against the original signal "
            "performs better than trading with it. See this script's module docstring."
        )

    print(f"\nFetching price history for {price_ticker}...")
    try:
        price_history = _fetch_price_history(price_ticker)
    except Exception as exc:
        print(f"Could not fetch price history for '{price_ticker}': {exc}")
        return
    print(f"  Got {len(price_history)} daily closes.")

    correlation_result = run_backtest(
        signal_name=signal_label, asset=args.asset, signal_scores=signal_scores,
        price_history_oldest_first=price_history, forward_window_days=args.forward_days,
    )
    print(f"\n=== Correlation Backtest (does direction/magnitude line up with forward returns?) ===")
    print(f"  Sample size:         {correlation_result.sample_size} (skipped {correlation_result.skipped_dates})")
    print(f"  Correlation:         {correlation_result.correlation}")
    print(f"  Significance thresh: {correlation_result.significance_threshold}")
    print(f"  Likely significant:  {correlation_result.likely_significant}")
    print(f"\n  {correlation_result.interpretation()}")

    strategy_result = simulate_strategy(
        signal_name=signal_label, asset=args.asset, signal_scores=signal_scores,
        price_history_oldest_first=price_history, forward_window_days=args.forward_days,
        entry_threshold=0.0,  # every fired signal IS the entry criterion already — no further filtering by default
        transaction_cost_bps=args.transaction_cost_bps,
    )
    print(f"\n=== Strategy Backtest (if you'd traded every fired signal) ===")
    print(f"  Trades:           {strategy_result.num_trades} ({strategy_result.num_wins}W / {strategy_result.num_losses}L)")
    print(f"  Win rate:         {strategy_result.win_rate}%")
    print(f"  Profit factor:    {strategy_result.profit_factor}")
    print(f"  Total return:     {strategy_result.total_return_pct}%  (compounded)")
    print(f"  Max strategy DD:  {strategy_result.max_drawdown_pct}%")
    print(f"  Sharpe ratio:     {strategy_result.sharpe_ratio}")
    print(f"  Sortino ratio:    {strategy_result.sortino_ratio}")
    print(f"\n  {strategy_result.interpretation()}")

    print(f"\n=== Signal Log ===")
    for d, score in signal_scores:
        direction = "BULLISH" if score > 0 else "BEARISH"
        print(f"  {d}  {direction:<8}  confidence={abs(score):.1f}")


if __name__ == "__main__":
    main()
