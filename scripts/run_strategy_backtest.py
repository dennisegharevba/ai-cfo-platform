"""
Run a strategy-level backtest: simulate actual trades from a signal and
report real strategy performance (Sharpe, Sortino, win rate, profit
factor, strategy-level max drawdown) — not just correlation.

Per docs/ARCHITECTURE_STRATEGY_BACKTESTING.md: this is still purely
research. It simulates a hypothetical, unmanaged strategy (fixed holding
period, one unit per trade, a flat transaction-cost estimate) — it does
not place trades, connect to a broker, or manage a real position.

Reuses the exact same signal-computation infrastructure as
scripts/run_backtest.py (SIGNAL_FUNCTIONS, price fetching, FRED rate
pacing) — only the final step (correlation vs. simulated trades) differs.

Run:
    python scripts/run_strategy_backtest.py --signal seasonality --asset Gold
    python scripts/run_strategy_backtest.py --signal "Initial Jobless Claims" --asset SPY --entry-threshold 20
    python scripts/run_strategy_backtest.py --signal vix --asset SPY --transaction-cost-bps 10

Needs real network access (and a real FRED_API_KEY for anything but
seasonality) — cannot produce a real answer from a sandbox with no
network access.
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import FRED_API_KEY
from scripts.run_backtest import SIGNAL_FUNCTIONS, _resolve_price_ticker, _fetch_price_history, _needs_fred_pacing
from agents.strategy_backtest import simulate_strategy


def main():
    parser = argparse.ArgumentParser(description="Simulate actual trades from a signal and report real strategy performance.")
    parser.add_argument("--signal", required=True, choices=list(SIGNAL_FUNCTIONS.keys()))
    parser.add_argument("--asset", required=True)
    parser.add_argument("--price-ticker", default=None)
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to 5 years ago")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--step-days", type=int, default=20, help="Spacing between signal checks")
    parser.add_argument("--forward-days", type=int, default=20, help="Holding period per trade")
    parser.add_argument("--entry-threshold", type=float, default=15.0, help="Minimum |signal score| to trigger a trade")
    parser.add_argument("--transaction-cost-bps", type=float, default=5.0, help="Round-trip transaction cost estimate, in basis points")
    parser.add_argument("--request-delay", type=float, default=0.6)
    args = parser.parse_args()

    if args.signal != "seasonality" and not FRED_API_KEY:
        print(f"FRED_API_KEY is not set — the '{args.signal}' signal needs it. Set it in .env and re-run.")
        return

    price_ticker = _resolve_price_ticker(args.asset, args.price_ticker)
    print(f"\nFetching price history for {price_ticker}" +
          (f" (resolved from --asset '{args.asset}')" if price_ticker != args.asset else "") + "...")
    try:
        price_history = _fetch_price_history(price_ticker)
    except Exception as exc:
        print(f"Could not fetch price history for '{price_ticker}': {exc}")
        return
    print(f"  Got {len(price_history)} daily closes.")

    end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else end_date - timedelta(days=365 * 5)
    test_dates = []
    d = start_date
    while d <= end_date:
        test_dates.append(d)
        d += timedelta(days=args.step_days)

    print(f"\nComputing '{args.signal}' signal for {len(test_dates)} historical dates...")
    signal_fn = SIGNAL_FUNCTIONS[args.signal]
    paced = _needs_fred_pacing(args.signal)
    signal_scores = []
    for i, d in enumerate(test_dates):
        score = signal_fn(d, args.asset)
        if score is not None:
            signal_scores.append((d, score))
        if paced and i < len(test_dates) - 1:
            time.sleep(args.request_delay)
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(test_dates)} dates processed")

    result = simulate_strategy(
        signal_name=args.signal, asset=args.asset, signal_scores=signal_scores,
        price_history_oldest_first=price_history, forward_window_days=args.forward_days,
        entry_threshold=args.entry_threshold, transaction_cost_bps=args.transaction_cost_bps,
    )

    print(f"\n=== Strategy Backtest Result ===")
    print(f"  Signal:              {result.signal_name}")
    print(f"  Asset:               {result.asset}")
    print(f"  Entry threshold:     |score| >= {result.entry_threshold}")
    print(f"  Holding period:      {result.forward_window_days} days")
    print(f"  Transaction cost:    {result.transaction_cost_bps} bps round-trip")
    print(f"  Trades:              {result.num_trades} ({result.num_wins}W / {result.num_losses}L), skipped {result.skipped_dates}")
    print(f"  Win rate:            {result.win_rate}%")
    print(f"  Profit factor:       {result.profit_factor}")
    print(f"  Total return:        {result.total_return_pct}%  (compounded)")
    print(f"  Max strategy DD:     {result.max_drawdown_pct}%")
    print(f"  Sharpe ratio:        {result.sharpe_ratio}")
    print(f"  Sortino ratio:       {result.sortino_ratio}")
    print(f"\n  {result.interpretation()}")

    if result.trades:
        print(f"\n=== Trade Log ===")
        for t in result.trades:
            print(f"  {t.entry_date} -> {t.exit_date}  {t.direction.upper():<5}  "
                  f"score={t.signal_score_at_entry:+.1f}  net={t.net_return_pct:+.2f}%  {'WIN' if t.is_win else 'loss'}")


if __name__ == "__main__":
    main()
