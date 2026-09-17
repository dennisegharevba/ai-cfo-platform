from unittest.mock import patch, MagicMock

import pytest

from brokers.alpaca_connector import AlpacaConnector, PAPER_BASE_URL, LIVE_BASE_URL
from brokers.broker_interface import BrokerError
from models.order import Order, OrderSide, OrderType


def _mock_response(json_data, status_ok=True, status_code=200, reason="OK", text="{}"):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.ok = status_ok
    resp.status_code = status_code
    resp.reason = reason
    resp.text = text
    return resp


# --- THE safety model: this is the most important set of tests in this project ---

def test_default_construction_is_always_paper():
    c = AlpacaConnector(api_key="k", api_secret="s")
    assert c.is_paper is True
    assert c.base_url == PAPER_BASE_URL


def test_explicit_false_is_still_paper():
    c = AlpacaConnector(api_key="k", api_secret="s", live_trading_confirmed=False)
    assert c.is_paper is True
    assert c.base_url == PAPER_BASE_URL


def test_none_is_still_paper():
    c = AlpacaConnector(api_key="k", api_secret="s", live_trading_confirmed=None)
    assert c.is_paper is True


@pytest.mark.parametrize("sneaky_value", [1, "True", "true", "yes", "live", [1], {"live": True}, 1.0])
def test_no_truthy_non_boolean_value_can_enable_live_trading(sneaky_value):
    """
    THE critical safety test: only the literal Python boolean True may
    enable live trading. Every other truthy-looking value — an integer,
    a string, a non-empty collection — must still result in paper
    trading. A typo or a config value that LOOKS like it should mean
    "yes" must never accidentally arm live trading.
    """
    c = AlpacaConnector(api_key="k", api_secret="s", live_trading_confirmed=sneaky_value)
    assert c.is_paper is True, f"SAFETY FAILURE: {sneaky_value!r} enabled live trading!"
    assert c.base_url == PAPER_BASE_URL


def test_only_literal_true_enables_live_trading():
    c = AlpacaConnector(api_key="k", api_secret="s", live_trading_confirmed=True)
    assert c.is_paper is False
    assert c.base_url == LIVE_BASE_URL


def test_missing_credentials_raise_before_any_request():
    with pytest.raises(BrokerError):
        AlpacaConnector(api_key="", api_secret="s")
    with pytest.raises(BrokerError):
        AlpacaConnector(api_key="k", api_secret="")


# --- account / positions ---

def test_get_account_reports_is_paper_correctly():
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response({"equity": "100000", "cash": "50000", "buying_power": "100000"})):
        c = AlpacaConnector(api_key="k", api_secret="s")
        account = c.get_account()
    assert account.equity == 100000.0
    assert account.is_paper is True


def test_get_positions_parses_real_shape():
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response([
                   {"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.0", "current_price": "155.0"},
               ])):
        c = AlpacaConnector(api_key="k", api_secret="s")
        positions = c.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == 10.0


# --- order submission: the never-raise-uncaught guarantee ---

def test_successful_order_submission():
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response({"id": "order-123", "status": "new"})):
        c = AlpacaConnector(api_key="k", api_secret="s")
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        result = c.submit_order(order)
    assert result.broker_order_id == "order-123"
    assert result.status.value == "submitted"


def test_rejected_order_returns_cleanly_never_raises():
    """A rejection is a real, expected outcome — must come back as a
    normal Order with status=REJECTED, never as an uncaught exception
    that could crash an unattended execution loop."""
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response({"message": "insufficient buying power"}, status_ok=False, status_code=403, reason="Forbidden")):
        c = AlpacaConnector(api_key="k", api_secret="s")
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=100000)
        result = c.submit_order(order)  # must not raise
    assert result.status.value == "rejected"
    assert "insufficient buying power" in result.rejection_reason


def test_network_failure_during_submit_is_reported_as_rejection_not_uncaught():
    import requests as requests_module
    with patch("brokers.alpaca_connector.requests.request", side_effect=requests_module.ConnectionError("boom")):
        c = AlpacaConnector(api_key="k", api_secret="s")
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        result = c.submit_order(order)  # must not raise
    assert result.status.value == "rejected"


def test_limit_order_includes_limit_price_in_request_body():
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response({"id": "order-1", "status": "new"})) as mock_req:
        c = AlpacaConnector(api_key="k", api_secret="s")
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, order_type=OrderType.LIMIT, limit_price=150.0)
        c.submit_order(order)
    _, kwargs = mock_req.call_args
    assert kwargs["json"]["limit_price"] == "150.0"


def test_cancel_order_returns_true_on_success():
    with patch("brokers.alpaca_connector.requests.request", return_value=_mock_response({})):
        c = AlpacaConnector(api_key="k", api_secret="s")
        assert c.cancel_order("order-123") is True


def test_cancel_order_returns_false_on_failure_not_uncaught_exception():
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response({"message": "order not found"}, status_ok=False, status_code=404, reason="Not Found")):
        c = AlpacaConnector(api_key="k", api_secret="s")
        assert c.cancel_order("nonexistent") is False


# --- error reporting reads the real body, same lesson as telegram_alerter.py's earlier fix ---

def test_http_error_with_message_body_surfaces_the_real_reason():
    with patch("brokers.alpaca_connector.requests.request",
               return_value=_mock_response({"message": "account is restricted from trading"}, status_ok=False, status_code=403, reason="Forbidden")):
        c = AlpacaConnector(api_key="k", api_secret="s")
        with pytest.raises(BrokerError, match="account is restricted from trading"):
            c.get_account()
