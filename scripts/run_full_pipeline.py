"""
The full pipeline, end to end: real price history -> real volatility ->
real vol-target portfolio weights -> real broker account state -> a real
rebalance plan. Ties together agents/portfolio_construction.py and
agents/execution_engine.py against a real (paper) Alpaca account,
reusing every already-tested piece rather than duplicating any of it.

SAFETY: dry_run is the default, exactly like every other script in this
layer. Add --submit to actually place the planned orders — still paper
only, still no live-trading flag anywhere in this script.

Run:
    python scripts/run_full_pipeline.py --assets "AAPL:AAPL,SPY:SPY"
    python scripts/run_full_pipeline.py --assets "AAPL:AAPL,SPY:SPY" --submit
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ALPACA_API_KEY, ALPACA_API_SECRET
from scripts.run_backtest import _fetch_price_history
from agents.risk_calculations import annualized_volatility
from agents.portfolio_construction import volatility_target_weights, apply_position_constraints
from agents.execution_engine import plan_rebalance, execute_rebalance


def main():
    parser = argparse.ArgumentParser(description="Full pipeline: real data -> real allocation -> real broker state -> a rebalance plan.")
    parser.add_argument("--assets", required=True, help='Comma-separated "Label:Ticker" pairs, e.g. "AAPL:AAPL,SPY:SPY"')
    parser.add_argument("--max-position-pct", type=float, default=35.0)
    parser.add_argument("--max-gross-exposure-pct", type=float, default=100.0)
    parser.add_argument("--min-order-value", type=float, default=100.0)
    parser.add_argument("--submit", action="store_true", help="Actually submit the plan to your PAPER account. Without this flag, the plan is only shown (dry run).")
    args = parser.parse_args()

    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        print("ALPACA_API_KEY / ALPACA_API_SECRET are not set in .env. Set them and re-run.")
        return

    pairs = []
    for entry in args.assets.split(","):
        entry = entry.strip()
        if ":" not in entry:
            print(f"Skipping '{entry}' — expected the format Label:Ticker")
            continue
        label, ticker = entry.split(":", 1)
        pairs.append((label.strip(), ticker.strip()))
    if not pairs:
        print("No valid Label:Ticker pairs found in --assets.")
        return

    # --- Step 1: real price history -> real volatility, per asset ---
    print("=== Step 1: fetching real price history and computing volatility ===")
    volatilities, current_prices = {}, {}
    for label, ticker in pairs:
        print(f"\n{label} ({ticker})...")
        try:
            history = _fetch_price_history(ticker)
        except Exception as exc:
            print(f"  Could not fetch: {exc} — excluding.")
            continue
        if len(history) < 2:
            print("  Not enough history — excluding.")
            continue
        closes = [price for _date, price in history]
        current_prices[label] = closes[-1]
        daily_returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
        vol = annualized_volatility(daily_returns)
        if vol is None:
            print("  Could not compute volatility — excluding.")
            continue
        volatilities[label] = vol
        print(f"  {len(closes)} closes, annualized vol {vol:.2f}%, current price ${closes[-1]:.2f}")

    if not volatilities:
        print("\nNo assets had usable data — stopping.")
        return

    # --- Step 2: real vol-target weights + constraints ---
    print("\n=== Step 2: building the target allocation ===")
    raw_weights = volatility_target_weights(volatilities)
    target_weights = apply_position_constraints(
        raw_weights, max_position_pct=args.max_position_pct, max_gross_exposure_pct=args.max_gross_exposure_pct,
    )
    for label, w in target_weights.items():
        print(f"  {label}: {w:.2f}%")

    # --- Step 3: real broker state ---
    print("\n=== Step 3: connecting to your real (paper) Alpaca account ===")
    from brokers.alpaca_connector import AlpacaConnector
    broker = AlpacaConnector(api_key=ALPACA_API_KEY, api_secret=ALPACA_API_SECRET)  # paper — always, this script never passes live_trading_confirmed
    assert broker.is_paper, "SAFETY FAILURE: this script must never connect to a live account."
    try:
        account = broker.get_account()
        current_positions = broker.get_positions()
    except Exception as exc:
        print(f"Could not connect to Alpaca: {exc}")
        return
    print(f"  Equity: ${account.equity:,.2f}  |  Current positions: {[(p.symbol, p.quantity) for p in current_positions] or 'none'}")

    # --- Step 4: plan the rebalance ---
    print("\n=== Step 4: planning the rebalance ===")
    planned = plan_rebalance(
        target_weights_pct=target_weights, current_positions=current_positions,
        account_equity=account.equity, current_prices=current_prices, min_order_value=args.min_order_value,
    )
    if not planned:
        print("  No rebalancing needed — current positions already match the target.")
        return
    for p in planned:
        print(f"  {p.symbol:<8} {p.side.value.upper():<6} {p.quantity:>10.2f}  {p.reason}")

    # --- Step 5: dry run (default) or real submission (--submit) ---
    if not args.submit:
        print("\n=== Step 5: DRY RUN — nothing submitted. Add --submit to actually place these orders (paper account). ===")
        execute_rebalance(broker, planned, dry_run=True)
        return

    print("\n=== Step 5: submitting to your PAPER account ===")
    results = execute_rebalance(broker, planned, dry_run=False)
    for o in results:
        print(f"  {o.symbol}: {o.status.value}" + (f"  ({o.rejection_reason})" if o.rejection_reason else f"  id={o.broker_order_id}"))


if __name__ == "__main__":
    main()
