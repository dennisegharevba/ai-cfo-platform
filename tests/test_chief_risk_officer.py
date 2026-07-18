import random
from datetime import datetime, timezone

from agents.chief_risk_officer import ChiefRiskOfficer
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.portfolio import Portfolio, Position
from models.report import Bias, RiskLevel


class FakePriceHistorySource(DataSource):
    """Returns a payload shaped like YahooHistoryConnector's output."""
    name = "FAKE_PRICE_HISTORY"
    default_ttl_seconds = 3600

    def __init__(self, closes_oldest_to_newest):
        self.closes = closes_oldest_to_newest

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.closes))
        history = [{"date": f"day-{i}", "close": c} for i, c in enumerate(newest_first)]
        payload = {"ticker": "TEST", "latest_close": newest_first[0], "latest_date": "day-0", "history": history}
        return payload, datetime.now(timezone.utc)


def _stable_walk(start, n, seed, daily_move=0.01):
    random.seed(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + random.uniform(-daily_move, daily_move)))
    return closes


def test_concentrated_portfolio_flags_concentration_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_BIG", primary=FakePriceHistorySource(_stable_walk(100, 60, seed=1)))
    manager.register("PRICE_HISTORY_SMALL", primary=FakePriceHistorySource(_stable_walk(100, 60, seed=2)))

    portfolio = Portfolio(name="Concentrated", positions=[
        Position(symbol="BIG", quantity=1000),   # ~100,000 market value
        Position(symbol="SMALL", quantity=1),    # ~100 market value
    ])
    report = ChiefRiskOfficer(manager).analyze_portfolio(portfolio)

    assert report.bias == Bias.NEUTRAL
    assert report.bias_score == 0.0
    assert report.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)
    assert any("concentrat" in r.lower() for r in report.risks)


def test_balanced_portfolio_no_concentration_flag():
    manager = DataIntegrityManager(min_quality_threshold=50)
    for sym in ("A", "B", "C"):
        manager.register(f"PRICE_HISTORY_{sym}", primary=FakePriceHistorySource(_stable_walk(100, 60, seed=hash(sym) % 1000)))

    portfolio = Portfolio(name="Balanced", positions=[
        Position(symbol="A", quantity=100),
        Position(symbol="B", quantity=100),
        Position(symbol="C", quantity=100),
    ])
    report = ChiefRiskOfficer(manager).analyze_portfolio(portfolio)
    assert not any("concentrat" in r.lower() for r in report.risks)


def test_highly_correlated_positions_flagged():
    manager = DataIntegrityManager(min_quality_threshold=50)
    shared_walk = _stable_walk(100, 60, seed=42)
    # Two positions with IDENTICAL price paths -> correlation should be ~1.0
    manager.register("PRICE_HISTORY_TWIN1", primary=FakePriceHistorySource(shared_walk))
    manager.register("PRICE_HISTORY_TWIN2", primary=FakePriceHistorySource(shared_walk))

    portfolio = Portfolio(name="Twins", positions=[
        Position(symbol="TWIN1", quantity=100),
        Position(symbol="TWIN2", quantity=100),
    ])
    report = ChiefRiskOfficer(manager).analyze_portfolio(portfolio)
    assert any("correlation" in e.lower() for e in report.evidence)
    assert any("correlation" in r.lower() and "high" in r.lower() for r in report.risks)
    assert report.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)


def test_severe_drawdown_flagged_high_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    # A sharp, sustained decline: 100 -> 50 over the window
    crash = [100 - i * 0.85 for i in range(59)]
    manager.register("PRICE_HISTORY_CRASH", primary=FakePriceHistorySource(crash))

    portfolio = Portfolio(name="Crashing", positions=[Position(symbol="CRASH", quantity=100)])
    report = ChiefRiskOfficer(manager).analyze_portfolio(portfolio)
    assert report.risk_level == RiskLevel.HIGH
    assert any("drawdown" in r.lower() for r in report.risks)


def test_missing_all_price_data_yields_zero_confidence_high_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    portfolio = Portfolio(name="Empty Data", positions=[Position(symbol="NODATA", quantity=100)])
    report = ChiefRiskOfficer(manager).analyze_portfolio(portfolio)
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True


def test_partial_price_data_reduces_confidence_but_still_reports():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_HAS_DATA", primary=FakePriceHistorySource(_stable_walk(100, 60, seed=7)))
    # PRICE_HISTORY_NO_DATA never registered
    portfolio = Portfolio(name="Partial", positions=[
        Position(symbol="HAS_DATA", quantity=100),
        Position(symbol="NO_DATA", quantity=100),
    ])
    report = ChiefRiskOfficer(manager).analyze_portfolio(portfolio)
    assert report.is_degraded() is True
    assert any("NO_DATA" in gap for gap in report.data_gaps)
    assert 0.0 < report.confidence < 70.0
    assert len(report.evidence) > 0  # still produces a real assessment from the data it does have
