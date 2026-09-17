"""
Order/Fill models — the shared vocabulary for the execution layer.

This is the first component in this platform that touches real capital
if misused. See docs/ARCHITECTURE_EXECUTION_LAYER.md for the full safety
model before using anything built on top of these models. In short:
PAPER TRADING ONLY is wired in right now — live trading is deliberately
not connected, pending a separate, explicit decision once paper trading
has been genuinely exercised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    PENDING = "pending"              # built locally, not yet submitted to a broker
    SUBMITTED = "submitted"          # sent to the broker, awaiting fill
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    timestamp: datetime


@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: Optional[str] = None
    fills: List[Fill] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("A LIMIT order requires a limit_price")
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")

    @property
    def filled_quantity(self) -> float:
        return sum(f.quantity for f in self.fills)

    @property
    def average_fill_price(self) -> Optional[float]:
        if not self.fills:
            return None
        total_value = sum(f.quantity * f.price for f in self.fills)
        return round(total_value / self.filled_quantity, 4)

    @property
    def is_complete(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "status": self.status.value,
            "broker_order_id": self.broker_order_id,
            "filled_quantity": self.filled_quantity,
            "average_fill_price": self.average_fill_price,
            "rejection_reason": self.rejection_reason,
        }
