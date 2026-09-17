"""
Alpaca broker connector.

CRITICAL SAFETY MODEL — read before using:

1. PAPER TRADING IS THE ONLY DEFAULT. Constructing AlpacaConnector with
   no further arguments ALWAYS uses Alpaca's paper endpoint
   (paper-api.alpaca.markets), regardless of anything in .env.

2. Live trading requires `live_trading_confirmed=True` passed EXPLICITLY
   to the constructor, in code, every time. This is deliberately NOT
   readable from an environment variable or .env setting — a config
   value can sit forgotten in a file for months (see this project's own
   TELEGRAM_BOT_TOKEN duplicate-key incident); a live-trading switch
   needs a human to consciously write it in code each time, not
   something that persists silently.

3. HONEST, IMPORTANT CAVEAT — unlike every other connector in this
   project (FRED, EIA, CFTC, SEC, Yahoo, Telegram), this one has NOT
   been verified against a real API response. Every other connector in
   this platform was built, then LIVE-TESTED by a real user with real
   credentials, and real bugs were found and fixed as a direct result
   (see docs/ for the full history). This connector cannot be tested
   that way from this environment — no network access, no real Alpaca
   account. Its request/response shapes are built from Alpaca's
   documented, stable REST API conventions, not confirmed against a
   live response. Treat it with real skepticism and test it extensively
   against the PAPER endpoint — never live — before trusting it for
   anything.

Docs (for your own verification, not fetched from here):
https://docs.alpaca.markets/reference/getaccount
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import requests

from brokers.broker_interface import BrokerAccount, BrokerError, BrokerInterface, BrokerPosition
from models.order import Fill, Order, OrderSide, OrderStatus, OrderType

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"


class AlpacaConnector(BrokerInterface):
    def __init__(
        self, api_key: str, api_secret: str, live_trading_confirmed: bool = False, timeout: int = 15,
    ):
        """
        live_trading_confirmed: MUST be explicitly passed as True, in
        code, to use the live endpoint. Any other value — missing,
        False, None, a truthy-looking string — uses paper. There is no
        way to enable live trading through .env or any environment
        variable; this is deliberate. See this module's docstring.
        """
        if not api_key or not api_secret:
            raise BrokerError("Alpaca API key and secret must both be provided")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self._is_paper = live_trading_confirmed is not True  # anything other than the literal True -> paper
        self.base_url = LIVE_BASE_URL if live_trading_confirmed is True else PAPER_BASE_URL

    @property
    def is_paper(self) -> bool:
        return self._is_paper

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.api_secret}

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise BrokerError(f"Alpaca {method} {path} request failed: {exc}") from exc

        try:
            data = resp.json() if resp.text else {}
        except ValueError:
            data = None

        if not resp.ok:
            # Same lesson as telegram/telegram_alerter.py's fix earlier in
            # this project: read the real error body before raising, so
            # the actual reason is visible rather than a bare status code.
            if data and "message" in data:
                raise BrokerError(f"Alpaca API rejected the request: {data['message']}")
            raise BrokerError(f"Alpaca {method} {path} failed: {resp.status_code} {resp.reason}")
        return data or {}

    def get_account(self) -> BrokerAccount:
        data = self._request("GET", "/v2/account")
        return BrokerAccount(
            equity=float(data["equity"]), cash=float(data["cash"]),
            buying_power=float(data["buying_power"]), is_paper=self.is_paper,
        )

    def get_positions(self) -> List[BrokerPosition]:
        data = self._request("GET", "/v2/positions")
        return [
            BrokerPosition(
                symbol=p["symbol"], quantity=float(p["qty"]),
                average_entry_price=float(p["avg_entry_price"]),
                current_price=float(p["current_price"]) if p.get("current_price") else None,
            )
            for p in data
        ]

    def submit_order(self, order: Order) -> Order:
        body = {
            "symbol": order.symbol, "qty": str(order.quantity),
            "side": order.side.value, "type": order.order_type.value, "time_in_force": "day",
        }
        if order.order_type == OrderType.LIMIT:
            body["limit_price"] = str(order.limit_price)

        try:
            data = self._request("POST", "/v2/orders", json=body)
        except BrokerError as exc:
            # A rejection is a REAL, expected outcome — return it on the
            # order, never raise it uncaught (see BrokerInterface's
            # submit_order docstring for why this matters).
            order.status = OrderStatus.REJECTED
            order.rejection_reason = str(exc)
            return order

        order.broker_order_id = data.get("id")
        order.status = self._map_status(data.get("status", "new"))
        return order

    def get_order_status(self, broker_order_id: str) -> Order:
        data = self._request("GET", f"/v2/orders/{broker_order_id}")
        order = Order(
            symbol=data["symbol"], side=OrderSide(data["side"]),
            quantity=float(data["qty"]), order_type=OrderType(data["type"]),
            limit_price=float(data["limit_price"]) if data.get("limit_price") else None,
        )
        order.broker_order_id = broker_order_id
        order.status = self._map_status(data.get("status", "new"))
        if data.get("filled_qty") and float(data["filled_qty"]) > 0:
            order.fills.append(Fill(
                order_id=broker_order_id, symbol=data["symbol"], side=OrderSide(data["side"]),
                quantity=float(data["filled_qty"]),
                price=float(data.get("filled_avg_price") or 0),
                timestamp=datetime.now(),
            ))
        return order

    def cancel_order(self, broker_order_id: str) -> bool:
        try:
            self._request("DELETE", f"/v2/orders/{broker_order_id}")
            return True
        except BrokerError:
            return False

    @staticmethod
    def _map_status(alpaca_status: str) -> OrderStatus:
        mapping = {
            "new": OrderStatus.SUBMITTED, "accepted": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.SUBMITTED, "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED, "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED, "rejected": OrderStatus.REJECTED,
        }
        return mapping.get(alpaca_status, OrderStatus.SUBMITTED)
