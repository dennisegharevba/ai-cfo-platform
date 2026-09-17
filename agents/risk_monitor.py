"""
Risk monitor — ties real broker state to the already-real Chief Risk
Officer and the circuit breaker, producing one snapshot of "what's my
risk right now, and should trading halt."

Read-only, by construction: every function here only READS broker state
(get_account, get_positions) — nothing in this module can place, modify,
or cancel an order. That's a meaningfully lower-risk surface than
agents/execution_engine.py, and is reflected in a lighter safety model
here (no dry-run flag needed, since there's nothing to dry-run).

Still an honest limitation shared with the rest of the execution layer:
this has not been exercised against a real broker from this environment
(no network access, no real account). The MATH (circuit breaker
thresholds, risk aggregation) is independently tested and verified; the
END-TO-END real-broker wiring has not been.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from brokers.broker_interface import BrokerInterface
from core.refresh_manager import DataIntegrityManager
from connectors.yahoo_history_connector import YahooHistoryConnector
from models.portfolio import Portfolio, Position
from models.report import AgentReport
from agents.chief_risk_officer import ChiefRiskOfficer
from agents.circuit_breaker import CircuitBreakerConfig, CircuitBreakerResult, check_circuit_breaker


@dataclass
class RiskMonitorSnapshot:
    account_equity: float
    is_paper: bool
    risk_report: Optional[AgentReport]
    circuit_breaker: CircuitBreakerResult


def build_portfolio_from_broker(broker: BrokerInterface) -> Portfolio:
    """Converts the broker's own real, current positions into this
    platform's existing Portfolio/Position shape — read-only, no side
    effect on the broker."""
    positions = broker.get_positions()
    return Portfolio(name="Live Broker Portfolio", positions=[
        Position(symbol=p.symbol, quantity=p.quantity) for p in positions
    ])


def take_risk_snapshot(
    broker: BrokerInterface, daily_starting_equity: float, peak_equity: float,
    circuit_breaker_config: CircuitBreakerConfig = None, min_quality: float = 60.0,
) -> RiskMonitorSnapshot:
    """
    daily_starting_equity, peak_equity: caller-tracked reference points
    for the circuit breaker (see agents.circuit_breaker's own docstring
    for why this function is stateless rather than tracking them itself).

    Fetches real account/positions from the broker (read-only), runs
    them through the existing, already-tested Chief Risk Officer for
    real VaR/volatility/correlation, and checks the circuit breaker
    against current equity. If NO positions are currently held, the
    Chief Risk Officer step is skipped entirely (nothing to analyze) and
    risk_report is None — not a fabricated empty report.
    """
    account = broker.get_account()

    portfolio = build_portfolio_from_broker(broker)
    risk_report = None
    if portfolio.positions:
        manager = DataIntegrityManager(min_quality_threshold=min_quality)
        risk_officer = ChiefRiskOfficer(manager, min_quality=min_quality)
        for position in portfolio.positions:
            key = risk_officer.price_history_key_for(position.symbol)
            if not manager.is_registered(key):
                manager.register(key, primary=YahooHistoryConnector(position.symbol))
        risk_report = risk_officer.analyze_portfolio(portfolio)

    breaker_result = check_circuit_breaker(
        current_equity=account.equity, daily_starting_equity=daily_starting_equity,
        peak_equity=peak_equity, config=circuit_breaker_config,
    )

    return RiskMonitorSnapshot(
        account_equity=account.equity, is_paper=account.is_paper,
        risk_report=risk_report, circuit_breaker=breaker_result,
    )
