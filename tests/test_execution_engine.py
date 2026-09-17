from agents.execution_engine import plan_rebalance, execute_rebalance
from brokers.broker_interface import BrokerPosition
from models.order import OrderSide, OrderStatus


class _ExplodingBroker:
    """A broker that raises if ANY method is called — used to prove
    dry-run mode never touches the broker at all."""
    def submit_order(self, order):
        raise AssertionError("submit_order should NEVER be called in dry-run mode!")

    def get_positions(self):
        raise AssertionError("get_positions should NEVER be called in dry-run mode!")


class _FakeBroker:
    def __init__(self):
        self.submitted = []

    def submit_order(self, order):
        self.submitted.append(order)
        order.status = OrderStatus.SUBMITTED
        order.broker_order_id = f"fake-{len(self.submitted)}"
        return order


# --- plan_rebalance math ---

def test_new_position_sized_correctly():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0}, current_positions=[],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    assert len(planned) == 1
    # $100k * 20% = $20k / $200 = 100 shares
    assert planned[0].quantity == 100.0
    assert planned[0].side == OrderSide.BUY
    assert planned[0].reason == "open new position"


def test_closing_a_position_not_in_the_new_target():
    """A symbol with a current position but no target weight at all
    should get a full closing order — the allocation no longer
    mentioning it means 'don't hold this,' not 'leave it untouched.'"""
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0},
        current_positions=[BrokerPosition(symbol="TLT", quantity=50.0, average_entry_price=90.0)],
        account_equity=100000, current_prices={"AAPL": 200.0, "TLT": 95.0},
    )
    tlt_order = next(p for p in planned if p.symbol == "TLT")
    assert tlt_order.side == OrderSide.SELL
    assert tlt_order.quantity == 50.0
    assert tlt_order.target_quantity == 0.0
    assert tlt_order.reason == "close position"


def test_increasing_an_existing_position():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 30.0},
        current_positions=[BrokerPosition(symbol="AAPL", quantity=50.0, average_entry_price=180.0)],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    order = planned[0]
    # target: $30k / $200 = 150 shares. current: 50. delta: +100.
    assert order.side == OrderSide.BUY
    assert order.quantity == 100.0
    assert order.reason == "increase position"


def test_reducing_an_existing_position():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 10.0},
        current_positions=[BrokerPosition(symbol="AAPL", quantity=100.0, average_entry_price=180.0)],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    order = planned[0]
    # target: $10k / $200 = 50 shares. current: 100. delta: -50.
    assert order.side == OrderSide.SELL
    assert order.quantity == 50.0
    assert order.reason == "reduce position"


def test_missing_price_skips_the_symbol_never_estimates():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0, "GHOST": 10.0}, current_positions=[],
        account_equity=100000, current_prices={"AAPL": 200.0},  # no price for GHOST
    )
    symbols = [p.symbol for p in planned]
    assert "GHOST" not in symbols
    assert "AAPL" in symbols


def test_trivial_rebalance_below_min_order_value_is_skipped():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.001},  # a tiny fraction different from current
        current_positions=[BrokerPosition(symbol="AAPL", quantity=100.0, average_entry_price=200.0)],
        account_equity=100000, current_prices={"AAPL": 200.0}, min_order_value=100.0,
    )
    assert planned == []  # the resulting order value is well under $100 -> skipped


def test_no_change_produces_no_order():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0},
        current_positions=[BrokerPosition(symbol="AAPL", quantity=100.0, average_entry_price=200.0)],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    assert planned == []


# --- execute_rebalance: the dry-run safety guarantee ---

def test_dry_run_never_touches_the_broker():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0}, current_positions=[],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    orders = execute_rebalance(_ExplodingBroker(), planned, dry_run=True)  # must not raise
    assert all(o.status == OrderStatus.PENDING for o in orders)


def test_dry_run_is_the_default():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0}, current_positions=[],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    orders = execute_rebalance(_ExplodingBroker(), planned)  # no dry_run argument at all -> must still not raise
    assert all(o.status == OrderStatus.PENDING for o in orders)


def test_explicit_dry_run_false_actually_submits():
    planned = plan_rebalance(
        target_weights_pct={"AAPL": 20.0}, current_positions=[],
        account_equity=100000, current_prices={"AAPL": 200.0},
    )
    broker = _FakeBroker()
    orders = execute_rebalance(broker, planned, dry_run=False)
    assert len(broker.submitted) == 1
    assert orders[0].status == OrderStatus.SUBMITTED
    assert orders[0].broker_order_id == "fake-1"
