from datetime import datetime, timezone
from typing import Dict, List

from agents.portfolio_agent_base import PortfolioAgent
from core.data_source import DataSource, DataSourceError
from core.refresh_manager import DataIntegrityManager
from models.portfolio import Portfolio, Position
from models.report import AgentReport, Bias, RiskLevel


class FakePriceSource(DataSource):
    name = "FAKE_PRICE"
    default_ttl_seconds = 300

    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    def fetch(self, **kwargs):
        if self.should_fail:
            raise DataSourceError("simulated failure")
        return {"latest_close": 100.0}, datetime.now(timezone.utc)


class DummyPortfolioAgent(PortfolioAgent):
    department = "Dummy Portfolio Agent"

    def price_history_key_for(self, symbol: str) -> str:
        return f"PRICE_{symbol}"

    def _build_report(self, usable_by_symbol: Dict, portfolio: Portfolio) -> AgentReport:
        return AgentReport(
            department=self.department,
            asset_or_theme=portfolio.name,
            bias=Bias.NEUTRAL,
            bias_score=0.0,
            confidence=100.0 if len(usable_by_symbol) == len(portfolio.positions) else 50.0,
            risk_level=RiskLevel.LOW,
            evidence=[f"saw {len(usable_by_symbol)} usable symbols"],
        )


def _portfolio(symbols):
    return Portfolio(name="Test Portfolio", positions=[Position(symbol=s, quantity=10) for s in symbols])


def test_all_symbols_usable_gives_full_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_AAPL", primary=FakePriceSource())
    manager.register("PRICE_MSFT", primary=FakePriceSource())
    agent = DummyPortfolioAgent(manager)
    report = agent.analyze_portfolio(_portfolio(["AAPL", "MSFT"]))
    assert report.confidence == 100.0
    assert report.data_gaps == []


def test_unregistered_symbol_flagged_as_gap():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_AAPL", primary=FakePriceSource())
    # PRICE_MSFT never registered
    agent = DummyPortfolioAgent(manager)
    report = agent.analyze_portfolio(_portfolio(["AAPL", "MSFT"]))
    assert report.confidence == 50.0
    assert any("PRICE_MSFT" in gap for gap in report.data_gaps)
    assert report.is_degraded() is True


def test_failed_symbol_source_flagged_as_gap():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_AAPL", primary=FakePriceSource())
    manager.register("PRICE_MSFT", primary=FakePriceSource(should_fail=True))
    agent = DummyPortfolioAgent(manager)
    report = agent.analyze_portfolio(_portfolio(["AAPL", "MSFT"]))
    assert report.confidence == 50.0
    assert any("PRICE_MSFT" in gap and "missing" in gap for gap in report.data_gaps)


def test_empty_portfolio_yields_no_gaps():
    manager = DataIntegrityManager(min_quality_threshold=50)
    agent = DummyPortfolioAgent(manager)
    report = agent.analyze_portfolio(_portfolio([]))
    assert report.data_gaps == []
    assert report.confidence == 100.0  # 0 usable == 0 positions, vacuously "all usable"
