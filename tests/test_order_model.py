from datetime import datetime

import pytest

from models.order import Order, OrderSide, OrderType, OrderStatus, Fill


def test_negative_quantity_rejected():
    with pytest.raises(ValueError):
        Order(symbol="AAPL", side=OrderSide.BUY, quantity=-5)


def test_zero_quantity_rejected():
    with pytest.raises(ValueError):
        Order(symbol="AAPL", side=OrderSide.BUY, quantity=0)


def test_limit_order_without_limit_price_rejected():
    with pytest.raises(ValueError):
        Order(symbol="AAPL", side=OrderSide.BUY, quantity=5, order_type=OrderType.LIMIT)


def test_limit_order_with_limit_price_accepted():
    o = Order(symbol="AAPL", side=OrderSide.BUY, quantity=5, order_type=OrderType.LIMIT, limit_price=150.0)
    assert o.limit_price == 150.0


def test_empty_order_has_no_fills_and_no_average_price():
    o = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    assert o.filled_quantity == 0
    assert o.average_fill_price is None
    assert o.is_complete is False


def test_average_fill_price_computed_correctly_across_multiple_fills():
    o = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    o.fills.append(Fill(order_id="1", symbol="AAPL", side=OrderSide.BUY, quantity=6, price=100.0, timestamp=datetime.now()))
    o.fills.append(Fill(order_id="1", symbol="AAPL", side=OrderSide.BUY, quantity=4, price=102.0, timestamp=datetime.now()))
    assert o.filled_quantity == 10
    # (6*100 + 4*102) / 10 = 100.8
    assert o.average_fill_price == 100.8


def test_is_complete_true_for_terminal_statuses():
    for status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
        o = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1)
        o.status = status
        assert o.is_complete is True


def test_is_complete_false_for_non_terminal_statuses():
    for status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
        o = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1)
        o.status = status
        assert o.is_complete is False


def test_to_dict_serializes_all_fields():
    o = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    d = o.to_dict()
    assert d["symbol"] == "AAPL"
    assert d["side"] == "buy"
    assert d["status"] == "pending"
    assert d["filled_quantity"] == 0
