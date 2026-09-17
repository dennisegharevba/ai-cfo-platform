from agents.risk_monitor import take_risk_snapshot, build_portfolio_from_broker
from agents.circuit_breaker import CircuitBreakerConfig
from brokers.broker_interface import BrokerAccount, BrokerPosition


class _FakeBroker:
    def __init__(self, equity, positions, is_paper=True):
        self._equity = equity
        self._positions = positions
        self._is_paper = is_paper

    def get_account(self):
        return BrokerAccount(equity=self._equity, cash=1000, buying_power=1000, is_paper=self._is_paper)

    def get_positions(self):
        return self._positions


def test_build_portfolio_from_broker_converts_positions_correctly():
    broker = _FakeBroker(equity=100000, positions=[
        BrokerPosition(symbol="AAPL", quantity=10, average_entry_price=150.0),
        BrokerPosition(symbol="SPY", quantity=-5, average_entry_price=500.0),  # a short
    ])
    portfolio = build_portfolio_from_broker(broker)
    assert len(portfolio.positions) == 2
    assert portfolio.symbols() == ["AAPL", "SPY"]
    short_position = next(p for p in portfolio.positions if p.symbol == "SPY")
    assert short_position.quantity == -5  # short quantity preserved as negative


def test_empty_portfolio_produces_no_risk_report_not_a_fabricated_one():
    broker = _FakeBroker(equity=100000, positions=[])
    snapshot = take_risk_snapshot(broker, daily_starting_equity=100000, peak_equity=100000)
    assert snapshot.risk_report is None


def test_non_empty_portfolio_produces_a_real_risk_report_object():
    """Cannot verify real Yahoo data from this environment (no network
    access) — but the risk_report object itself must exist and degrade
    gracefully (matching Chief Risk Officer's own already-tested
    behavior for an unreachable data source), never crash and never
    silently stay None when positions genuinely exist."""
    broker = _FakeBroker(equity=100000, positions=[
        BrokerPosition(symbol="AAPL", quantity=10, average_entry_price=150.0),
    ])
    snapshot = take_risk_snapshot(broker, daily_starting_equity=100000, peak_equity=100000)
    assert snapshot.risk_report is not None


def test_account_equity_and_is_paper_correctly_reported():
    broker = _FakeBroker(equity=54321.0, positions=[], is_paper=True)
    snapshot = take_risk_snapshot(broker, daily_starting_equity=54321.0, peak_equity=54321.0)
    assert snapshot.account_equity == 54321.0
    assert snapshot.is_paper is True


def test_circuit_breaker_correctly_wired_through_real_equity():
    """The circuit breaker check inside take_risk_snapshot() must use
    the broker's REAL, current equity — not a stale or hardcoded value."""
    broker = _FakeBroker(equity=90000, positions=[])
    snapshot = take_risk_snapshot(
        broker, daily_starting_equity=100000, peak_equity=105000,
        circuit_breaker_config=CircuitBreakerConfig(max_daily_loss_pct=5.0),
    )
    assert snapshot.circuit_breaker.should_halt is True
    assert snapshot.circuit_breaker.daily_pnl_pct == -10.0


def test_no_halt_when_equity_is_healthy():
    broker = _FakeBroker(equity=101000, positions=[])
    snapshot = take_risk_snapshot(broker, daily_starting_equity=100000, peak_equity=101000)
    assert snapshot.circuit_breaker.should_halt is False


def test_never_calls_any_order_placing_method():
    """This module is documented as read-only — proven directly with a
    broker whose only order-related method raises if called at all."""
    class _OrderExplodingBroker(_FakeBroker):
        def submit_order(self, order):
            raise AssertionError("risk_monitor must NEVER call submit_order — it is read-only by design!")

    broker = _OrderExplodingBroker(equity=100000, positions=[])
    take_risk_snapshot(broker, daily_starting_equity=100000, peak_equity=100000)  # must not raise
