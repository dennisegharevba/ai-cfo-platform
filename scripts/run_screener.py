"""
Scan many assets across equities, commodities, FX, and crypto, rank them
by real technical conviction (see agents/opportunity_screener.py's module
docstring for exactly what "conviction" does and doesn't mean — it is
NOT a backtested win-probability), and optionally build a real
vol-target allocation and rebalance plan from the top candidates.

Reuses the platform's existing curated asset universe
(config/watchlist.py's COMMODITY_YAHOO_TICKERS / FX_YAHOO_TICKERS /
CRYPTO_YAHOO_TICKERS, config/sp500_tickers.py's LARGE_CAP_TICKERS) rather
than inventing a new list, and the already-tested
agents/portfolio_construction.py + agents/execution_engine.py for
everything after ranking — no duplicated logic.

SAFETY: identical model to every other script in this layer. Building a
plan requires --build-portfolio; submitting it requires --submit on top
of that (dry-run is still the default even then). No live-trading flag
anywhere in this file.

Scanning ALL 357 equities plus every commodity/FX/crypto pair is a lot
of real Yahoo requests — --max-equities defaults to a smaller, faster
subset (50) rather than the full universe, with pacing between requests
to avoid rate-limiting, the same lesson already learned and fixed for
FRED requests earlier in this project (see
docs/ARCHITECTURE_BACKTEST_DATE_PARSING_FIX.md). Raise --max-equities
for a broader scan once you've seen how long a smaller one takes.

Run:
    python scripts/run_screener.py
    python scripts/run_screener.py --asset-classes commodity,fx,crypto --top-n 5
    python scripts/run_screener.py --max-equities 100 --min-confidence 50 --build-portfolio
    python scripts/run_screener.py --diversify --top-n-per-class 3 --build-portfolio
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.watchlist import COMMODITY_YAHOO_TICKERS, FX_YAHOO_TICKERS, CRYPTO_YAHOO_TICKERS
from config.sp500_tickers import LARGE_CAP_TICKERS
from scripts.run_backtest import _fetch_price_history, _fetch_price_and_volume_history
from agents.opportunity_screener import screen_asset, rank_opportunities, rank_opportunities_by_class
from agents.risk_calculations import annualized_volatility
from agents.portfolio_construction import volatility_target_weights, apply_position_constraints
from agents.execution_engine import plan_rebalance, execute_rebalance

# Alpaca's Trading API supports US equities and crypto only — confirmed
# via research, NOT forex or commodity/futures trading in any form. Found
# via live testing: --build-portfolio was including commodity and FX
# candidates in the target allocation and rebalance plan, producing
# orders like "NZD/USD BUY 29138.33" and "Natural Gas BUY 901.87" —
# mathematically correct given the dollar allocation, but for asset types
# this broker cannot trade under any circumstances. Had --submit been
# used, every one of those orders would have been rejected, or worse, an
# undefined/confusing failure. The SCREENING step still covers every
# asset class scanned — that's real, valuable signal regardless of
# whether it's directly executable via this specific broker — but
# --build-portfolio now filters to only what Alpaca can actually trade
# before constructing anything meant to be submitted.
ALPACA_TRADEABLE_ASSET_CLASSES = {"equity", "crypto"}


def _build_universe(asset_classes, max_equities):
    universe = []
    if "commodity" in asset_classes:
        universe += [(label, ticker, "commodity") for label, ticker in COMMODITY_YAHOO_TICKERS.items()]
    if "fx" in asset_classes:
        universe += [(label, ticker, "fx") for label, ticker in FX_YAHOO_TICKERS.items()]
    if "crypto" in asset_classes:
        universe += [(label, ticker, "crypto") for label, ticker in CRYPTO_YAHOO_TICKERS.items()]
    if "equity" in asset_classes:
        universe += [(t, t, "equity") for t in LARGE_CAP_TICKERS[:max_equities]]
    return universe


def main():
    parser = argparse.ArgumentParser(description="Cross-asset-class opportunity screener.")
    parser.add_argument("--asset-classes", default="commodity,fx,crypto,equity", help="Comma-separated subset of: commodity,fx,crypto,equity")
    parser.add_argument("--max-equities", type=int, default=50, help="Cap on how many of the 357 large-cap equities to scan (full universe is slow — see module docstring)")
    parser.add_argument("--min-confidence", type=float, default=40.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--diversify", action="store_true", help="Guarantee representation from every scanned asset class, instead of one global top-N that can legitimately come back from a single class")
    parser.add_argument("--top-n-per-class", type=int, default=3, help="Only used with --diversify")
    parser.add_argument("--request-delay", type=float, default=0.3)
    parser.add_argument("--build-portfolio", action="store_true", help="Build a real vol-target allocation + rebalance plan from the top-ranked candidates")
    parser.add_argument("--max-position-pct", type=float, default=25.0)
    parser.add_argument("--max-gross-exposure-pct", type=float, default=100.0)
    parser.add_argument("--submit", action="store_true", help="Requires --build-portfolio too. Actually submits the plan to your PAPER account.")
    args = parser.parse_args()

    asset_classes = [c.strip() for c in args.asset_classes.split(",")]
    universe = _build_universe(asset_classes, args.max_equities)
    if not universe:
        print(f"No assets to scan for --asset-classes '{args.asset_classes}'.")
        return

    print(f"Scanning {len(universe)} assets across {asset_classes}...\n")
    opportunities, volatilities, current_prices = [], {}, {}
    for i, (label, ticker, asset_class) in enumerate(universe):
        try:
            # Fetched once via the volume-aware function — both the
            # close-only view (for volatility/current-price, below) and
            # the volumes passed to screen_asset() come from this single
            # fetch, rather than doubling network requests per asset
            # (which would worsen the exact intermittent-failure problem
            # the retry logic in _fetch_price_history() was built to
            # address — see docs/ARCHITECTURE_FETCH_RETRY.md).
            full_history = _fetch_price_and_volume_history(ticker)
        except Exception as exc:
            print(f"  [{i + 1}/{len(universe)}] {label} ({ticker}): fetch failed — {exc}")
            continue

        history = [(d, close) for d, close, _vol in full_history]
        volumes = [vol for _d, _close, vol in full_history]
        opp = screen_asset(label, ticker, asset_class, history, volumes_oldest_first=volumes)
        if opp is not None:
            opportunities.append(opp)
            closes = [p for _d, p in history]
            if len(closes) >= 2:
                daily_returns = [(closes[j] / closes[j - 1]) - 1.0 for j in range(1, len(closes))]
                vol = annualized_volatility(daily_returns)
                if vol is not None:
                    volatilities[label] = vol
                    current_prices[label] = closes[-1]
            print(f"  [{i + 1}/{len(universe)}] {label} ({ticker}): {opp.direction} conviction={opp.conviction_score}")
        else:
            print(f"  [{i + 1}/{len(universe)}] {label} ({ticker}): insufficient history, skipped")

        if i < len(universe) - 1:
            time.sleep(args.request_delay)

    if args.diversify:
        ranked = rank_opportunities_by_class(opportunities, min_confidence=args.min_confidence, top_n_per_class=args.top_n_per_class)
        header = f"\n=== Top {args.top_n_per_class} Per Asset Class (min confidence {args.min_confidence}) ==="
    else:
        ranked = rank_opportunities(opportunities, min_confidence=args.min_confidence, top_n=args.top_n)
        header = f"\n=== Top {len(ranked)} Opportunities (min confidence {args.min_confidence}) ==="

    print(header)
    print(f"{'Label':<15} {'Class':<10} {'Direction':<10} {'Bias':>8} {'Confidence':>12} {'Own Vol %':>10} {'Conviction':>12}")
    print("-" * 82)
    for o in ranked:
        print(f"{o.label:<15} {o.asset_class:<10} {o.direction:<10} {o.bias_score:>8.1f} {o.confidence:>12.1f} {o.annualized_vol_pct:>10.1f} {o.conviction_score:>12.2f}")

    if not ranked:
        print("\nNo opportunities met the confidence threshold — nothing further to do.")
        return

    if not args.build_portfolio:
        print("\nAdd --build-portfolio to turn these into a real target allocation and rebalance plan.")
        return

    # --- filter to what Alpaca can actually trade before building anything executable ---
    tradeable = [o for o in ranked if o.asset_class in ALPACA_TRADEABLE_ASSET_CLASSES]
    excluded = [o for o in ranked if o.asset_class not in ALPACA_TRADEABLE_ASSET_CLASSES]
    if excluded:
        print(f"\n=== Manual Trading Candidates ({len(excluded)}) — not tradeable via Alpaca, consider another platform ===")
        print(f"{'Label':<15} {'Class':<10} {'Direction':<10} {'Bias':>8} {'Confidence':>12} {'Own Vol %':>10} {'Conviction':>12}")
        print("-" * 82)
        for o in excluded:
            print(f"{o.label:<15} {o.asset_class:<10} {o.direction:<10} {o.bias_score:>8.1f} {o.confidence:>12.1f} {o.annualized_vol_pct:>10.1f} {o.conviction_score:>12.2f}")
    if not tradeable:
        print("\nNone of the ranked candidates are in a tradeable asset class (equity or crypto) — nothing to build.")
        return

    # --- build a real vol-target allocation from the tradeable candidates ---
    print("\n=== Building target allocation ===")
    ranked_labels = {o.label for o in tradeable}
    ranked_vols = {label: vol for label, vol in volatilities.items() if label in ranked_labels}
    raw_weights = volatility_target_weights(ranked_vols)
    target_weights = apply_position_constraints(
        raw_weights, max_position_pct=args.max_position_pct, max_gross_exposure_pct=args.max_gross_exposure_pct,
    )
    for label, w in target_weights.items():
        print(f"  {label}: {w:.2f}%")

    from config.settings import ALPACA_API_KEY, ALPACA_API_SECRET
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        print("\nALPACA_API_KEY / ALPACA_API_SECRET are not set in .env — cannot connect to a real account to plan against.")
        return

    print("\n=== Connecting to your real (paper) Alpaca account ===")
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

    print("\n=== Planning the rebalance ===")
    planned = plan_rebalance(
        target_weights_pct=target_weights, current_positions=current_positions,
        account_equity=account.equity, current_prices=current_prices,
    )
    if not planned:
        print("  No rebalancing needed — current positions already match the target.")
        return
    for p in planned:
        print(f"  {p.symbol:<8} {p.side.value.upper():<6} {p.quantity:>10.2f}  {p.reason}")

    if not args.submit:
        print("\nDRY RUN — nothing submitted. Add --submit to actually place these orders (paper account).")
        execute_rebalance(broker, planned, dry_run=True)
        return

    print("\nSubmitting to your PAPER account...")
    results = execute_rebalance(broker, planned, dry_run=False)
    for o in results:
        print(f"  {o.symbol}: {o.status.value}" + (f"  ({o.rejection_reason})" if o.rejection_reason else f"  id={o.broker_order_id}"))


if __name__ == "__main__":
    main()
