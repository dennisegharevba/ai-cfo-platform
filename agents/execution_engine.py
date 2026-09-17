"""
Execution engine — converts a target portfolio allocation (from
agents/portfolio_construction.py) plus current broker positions into a
set of orders, and (optionally, explicitly) submits them.

SAFETY MODEL: execute_rebalance() defaults to dry_run=True. In dry-run
mode, no order is ever sent to the broker — planned orders are computed
and returned with status=PENDING only. This mirrors the exact pattern
already established and tested in telegram/telegram_alerter.py via
scripts/demo_execution_officer.py's --send-real flag: explicit,
conscious opt-in required before anything real happens, safe-by-default
otherwise. This applies EQUALLY to paper and live brokers — dry-run
protects against unintended paper orders too, not just live ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from brokers.broker_interface import BrokerInterface, BrokerPosition
from models.order import Order, OrderSide, OrderType


@dataclass
class PlannedOrder:
    symbol: str
    side: OrderSide
    quantity: float
    current_quantity: float
    target_quantity: float
    reason: str


def plan_rebalance(
    target_weights_pct: Dict[str, float],
    current_positions: List[BrokerPosition],
    account_equity: float,
    current_prices: Dict[str, float],
    min_order_value: float = 100.0,
) -> List[PlannedOrder]:
    """
    target_weights_pct: e.g. {"AAPL": 20.0, "SPY": 30.0} — the output
        shape of agents.portfolio_construction.apply_position_constraints().
    current_prices: symbol -> current price, needed to convert a dollar
        target into a share/unit quantity. A symbol with a target weight
        but no price here is SKIPPED, not silently sized as zero or
        estimated — see the test proving this.
    min_order_value: rebalance orders smaller than this (in dollars) are
        skipped entirely — avoids generating cost-inefficient orders for
        trivial differences between current and target.

    A symbol with a CURRENT position but no target weight (or a target
    of 0) gets a full CLOSING order — this is deliberate: an allocation
    that no longer mentions a symbol means "don't hold this," not
    "leave it untouched."
    """
    current_qty_by_symbol = {p.symbol: p.quantity for p in current_positions}
    all_symbols = set(target_weights_pct.keys()) | set(current_qty_by_symbol.keys())

    planned: List[PlannedOrder] = []
    for symbol in sorted(all_symbols):
        current_qty = current_qty_by_symbol.get(symbol, 0.0)
        target_weight = target_weights_pct.get(symbol, 0.0)

        if target_weight > 0 and symbol not in current_prices:
            continue  # never estimate a quantity from a missing price

        if target_weight > 0:
            target_dollar_value = account_equity * (target_weight / 100.0)
            target_qty = target_dollar_value / current_prices[symbol]
        else:
            target_qty = 0.0

        delta_qty = target_qty - current_qty
        if delta_qty == 0:
            continue

        order_price = current_prices.get(symbol)
        order_value = abs(delta_qty) * order_price if order_price else None
        if order_value is not None and order_value < min_order_value:
            continue

        side = OrderSide.BUY if delta_qty > 0 else OrderSide.SELL
        if target_qty == 0:
            reason = "close position"
        elif current_qty == 0:
            reason = "open new position"
        elif delta_qty > 0:
            reason = "increase position"
        else:
            reason = "reduce position"

        planned.append(PlannedOrder(
            symbol=symbol, side=side, quantity=round(abs(delta_qty), 4),
            current_quantity=current_qty, target_quantity=round(target_qty, 4), reason=reason,
        ))

    return planned


def execute_rebalance(
    broker: BrokerInterface, planned_orders: List[PlannedOrder], dry_run: bool = True,
) -> List[Order]:
    """
    dry_run=True (the default): builds real Order objects but NEVER
    calls broker.submit_order() — returns them with status=PENDING so
    the caller can inspect exactly what would happen. Set dry_run=False
    to actually submit. This flag does not change based on whether
    `broker` is a paper or live connector — dry-run is a genuinely
    separate, additional layer of protection, not a substitute for
    checking broker.is_paper before ever using a live-configured broker.
    """
    orders = [
        Order(symbol=p.symbol, side=p.side, quantity=p.quantity, order_type=OrderType.MARKET)
        for p in planned_orders
    ]
    if dry_run:
        return orders
    return [broker.submit_order(o) for o in orders]
