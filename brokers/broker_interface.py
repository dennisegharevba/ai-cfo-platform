"""
Abstract broker interface — defines what ANY broker connector must
implement, so the execution engine and everything above it stays
broker-agnostic. Adding a second broker later means writing one new
connector against this same interface, not touching anything downstream.

See docs/ARCHITECTURE_EXECUTION_LAYER.md for the platform's safety model
before implementing or using any concrete connector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from models.order import Order


@dataclass
class BrokerPosition:
    """A broker's own reported position — the ground truth to reconcile
    internal state against, not something this platform computes itself."""
    symbol: str
    quantity: float           # negative for a short
    average_entry_price: float
    current_price: Optional[float] = None


@dataclass
class BrokerAccount:
    equity: float
    cash: float
    buying_power: float
    is_paper: bool             # ALWAYS explicit — never left to be inferred or assumed


class BrokerError(Exception):
    pass


class BrokerInterface(ABC):
    """Every concrete broker connector must implement all of these."""

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """MUST be checkable independently of trust in any specific
        connector's internal config — every caller that submits an order
        should be able to confirm paper-vs-live before doing so, not just
        assume it based on which class was imported."""
        ...

    @abstractmethod
    def get_account(self) -> BrokerAccount:
        ...

    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submits the order and returns it with status/broker_order_id
        updated. Must NEVER silently swallow a rejection — a rejected
        order returns with status=REJECTED and a real rejection_reason,
        not a raised exception that could be accidentally uncaught, and
        not a silently-dropped order."""
        ...

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        ...
