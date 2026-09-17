"""
Build a proposed portfolio allocation across multiple real assets, using
volatility-target weighting and position constraints.

Fetches REAL price history for each asset, computes REAL annualized
volatility from it, derives inverse-volatility weights, then applies
position/gross-exposure constraints. Prints a proposed allocation —
still purely research/planning, not an executed trade.

For sizing a SINGLE signal-driven strategy specifically (Kelly-based,
from real simulated trade history), use
agents.portfolio_construction.kelly_fraction_from_backtest() directly
with a result from scripts/run_strategy_backtest.py — not wired into
this script, since combining a Kelly-sized single strategy with a
multi-asset vol-target allocation in one CLI invocation would conflate
two genuinely different sizing questions rather than composing them
clearly. Both functions are directly importable and composable in your
own script if you want to combine them.

Run:
    python scripts/build_portfolio.py --assets "Gold:GC=F,SPY:SPY,TLT:TLT"
    python scripts/build_portfolio.py --assets "Gold:GC=F,SPY:SPY" --max-position-pct 40 --max-gross-exposure-pct 100
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_backtest import _fetch_price_history
from agents.risk_calculations import annualized_volatility
from agents.portfolio_construction import volatility_target_weights, apply_position_constraints


def main():
    parser = argparse.ArgumentParser(description="Build a volatility-targeted portfolio allocation across real assets.")
    parser.add_argument("--assets", required=True, help='Comma-separated "Label:Ticker" pairs, e.g. "Gold:GC=F,SPY:SPY,TLT:TLT"')
    parser.add_argument("--max-position-pct", type=float, default=35.0, help="Max weight for any single asset")
    parser.add_argument("--max-gross-exposure-pct", type=float, default=100.0, help="Max total allocation (100 = fully invested, no leverage)")
    parser.add_argument("--lookback-days", type=int, default=252, help="How many recent daily closes to compute volatility from")
    args = parser.parse_args()

    pairs = []
    for entry in args.assets.split(","):
        entry = entry.strip()
        if ":" not in entry:
            print(f"Skipping '{entry}' — expected the format Label:Ticker, e.g. Gold:GC=F")
            continue
        label, ticker = entry.split(":", 1)
        pairs.append((label.strip(), ticker.strip()))

    if not pairs:
        print("No valid Label:Ticker pairs found in --assets.")
        return

    volatilities = {}
    for label, ticker in pairs:
        print(f"\nFetching price history for {label} ({ticker})...")
        try:
            history = _fetch_price_history(ticker)
        except Exception as exc:
            print(f"  Could not fetch '{ticker}': {exc} — excluding {label} from the allocation.")
            continue
        closes = [price for _date, price in history[-args.lookback_days:]]
        if len(closes) < 2:
            print(f"  Not enough price history for {label} — excluding from the allocation.")
            continue
        daily_returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
        vol = annualized_volatility(daily_returns)
        if vol is None:
            print(f"  Could not compute volatility for {label} — excluding from the allocation.")
            continue
        volatilities[label] = vol
        print(f"  {label}: {len(closes)} closes, annualized volatility {vol:.2f}%")

    if not volatilities:
        print("\nNo assets had usable data — no allocation to propose.")
        return

    raw_weights = volatility_target_weights(volatilities)
    final_weights = apply_position_constraints(
        raw_weights, max_position_pct=args.max_position_pct, max_gross_exposure_pct=args.max_gross_exposure_pct,
    )

    print(f"\n=== Proposed Allocation ===")
    print(f"{'Asset':<15} {'Volatility':>12} {'Vol-Target Wt':>15} {'Final Wt (constrained)':>24}")
    print("-" * 68)
    for label in volatilities:
        print(f"{label:<15} {volatilities[label]:>11.2f}% {raw_weights.get(label, 0):>14.2f}% {final_weights.get(label, 0):>23.2f}%")
    print("-" * 68)
    print(f"{'TOTAL':<15} {'':<12} {sum(raw_weights.values()):>14.2f}% {sum(final_weights.values()):>23.2f}%")

    print(
        f"\nThis is a PROPOSED, hypothetical allocation based on inverse volatility weighting — it "
        f"does not account for correlation between assets (see agents/portfolio_construction.py's "
        f"module docstring), and it is not an executed trade. To check the resulting portfolio's "
        f"actual risk profile (VaR, real correlation-aware volatility), convert these weights into "
        f"a models.portfolio.Portfolio and run it through Chief Risk Officer."
    )


if __name__ == "__main__":
    main()
