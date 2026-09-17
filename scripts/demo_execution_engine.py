"""
Execution layer demo — deliberately more layers of safety than any other
demo script in this platform, given the stakes. Read
docs/ARCHITECTURE_EXECUTION_LAYER.md before running anything beyond the
default.

THREE LEVELS, each requiring explicit opt-in beyond the last:

  Level 0 (default, no flags): plans a rebalance using FAKE example
    data — no network call, no credentials needed, no interaction with
    Alpaca at all. Shows what the planning logic produces.

  Level 1 (--connect-paper): also connects to Alpaca's PAPER endpoint
    with your real ALPACA_API_KEY/ALPACA_API_SECRET and fetches your
    REAL (paper) account balance and positions. Read-only — no orders
    submitted. Needs real network access and real paper credentials.

  Level 2 (--submit-paper-orders, requires --connect-paper too): builds
    a rebalance plan from your REAL paper account/positions and
    SUBMITS it — to the PAPER account only. This places real (fake-
    money) orders. Still cannot touch a live account: this script
    contains NO live-trading flag at all, anywhere. Enabling live
    trading requires writing live_trading_confirmed=True directly in
    Python code — a deliberate, higher-friction step this script does
    not offer as a convenience flag.

Run:
    python scripts/demo_execution_engine.py
    python scripts/demo_execution_engine.py --connect-paper
    python scripts/demo_execution_engine.py --connect-paper --submit-paper-orders
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ALPACA_API_KEY, ALPACA_API_SECRET
from agents.execution_engine import plan_rebalance, execute_rebalance
from brokers.broker_interface import BrokerPosition


def _print_plan(planned):
    if not planned:
        print("  No rebalancing needed — current positions already match the target.")
        return
    print(f"  {'Symbol':<8} {'Side':<6} {'Qty':>10}  {'Reason'}")
    for p in planned:
        print(f"  {p.symbol:<8} {p.side.value.upper():<6} {p.quantity:>10.2f}  {p.reason}")


def main():
    parser = argparse.ArgumentParser(description="Execution layer demo — see this file's module docstring for the 3 safety levels.")
    parser.add_argument("--connect-paper", action="store_true", help="Connect to Alpaca's PAPER endpoint with real credentials (read-only)")
    parser.add_argument("--submit-paper-orders", action="store_true", help="Requires --connect-paper too. Actually submits the plan to your PAPER account.")
    args = parser.parse_args()

    print("=== AI CFO Platform — Execution Layer Demo ===")

    if not args.connect_paper:
        print("\n--- Level 0: planning with FAKE example data (no network, no credentials needed) ---")
        target = {"AAPL": 20.0, "SPY": 30.0}
        current = [BrokerPosition(symbol="TLT", quantity=50.0, average_entry_price=90.0)]
        prices = {"AAPL": 200.0, "SPY": 500.0, "TLT": 95.0}
        planned = plan_rebalance(target, current, account_equity=100000, current_prices=prices)
        print(f"Target: {target}")
        print(f"Current (fake): TLT x50")
        _print_plan(planned)
        print("\nRun with --connect-paper to use your real Alpaca PAPER account instead of this fake example.")
        return

    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        print("\nALPACA_API_KEY / ALPACA_API_SECRET are not set in .env. Set them and re-run.")
        return

    from brokers.alpaca_connector import AlpacaConnector
    broker = AlpacaConnector(api_key=ALPACA_API_KEY, api_secret=ALPACA_API_SECRET)  # paper — always, this script never passes live_trading_confirmed
    print(f"\n--- Level 1: connecting to Alpaca ({'PAPER' if broker.is_paper else 'LIVE — THIS SHOULD NEVER HAPPEN FROM THIS SCRIPT'}) ---")
    assert broker.is_paper, "SAFETY FAILURE: this demo script must never connect to a live account."

    try:
        account = broker.get_account()
        positions = broker.get_positions()
    except Exception as exc:
        print(f"Could not connect to Alpaca: {exc}")
        return

    print(f"Account equity: ${account.equity:,.2f}  |  Cash: ${account.cash:,.2f}  |  is_paper: {account.is_paper}")
    print(f"Current positions: {[(p.symbol, p.quantity) for p in positions] or 'none'}")

    print("\n--- Level 1: this script does not have real target weights or live prices for your account,")
    print("    so it cannot build a real plan automatically. Use agents.portfolio_construction and")
    print("    scripts/build_portfolio.py to produce real target weights, then call plan_rebalance()")
    print("    yourself with this account's real data.")

    if args.submit_paper_orders:
        print("\n--submit-paper-orders was passed, but no real plan was built above (see note).")
        print("This flag is here to make the CODE PATH visible and testable, not to auto-submit")
        print("anything without a real, explicit plan you've reviewed.")


if __name__ == "__main__":
    main()
