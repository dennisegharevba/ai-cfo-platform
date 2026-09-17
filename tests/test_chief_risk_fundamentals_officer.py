from datetime import datetime, timezone

from agents.chief_risk_fundamentals_officer import ChiefRiskFundamentalsOfficer
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FakePriceSource(DataSource):
    """Returns a payload shaped exactly like YahooHistoryConnector's output."""
    name = "FAKE_YAHOO"
    default_ttl_seconds = 3600

    def __init__(self, closes_oldest_first):
        self.closes = closes_oldest_first

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.closes))
        history = [
            {"date": f"2026-06-{i+1:02d}", "close": c, "high": c, "low": c}
            for i, c in enumerate(newest_first)
        ]
        payload = {
            "ticker": "TEST", "latest_close": newest_first[0],
            "latest_date": history[0]["date"], "history": history,
        }
        return payload, datetime.now(timezone.utc)


def _stable_prices(n=30, base=100.0):
    """Low-volatility, gently rising price series."""
    return [base + i * 0.1 for i in range(n)]


def _volatile_prices(n=30, base=100.0):
    """High-volatility, wildly swinging price series."""
    prices = []
    for i in range(n):
        prices.append(base + (30 if i % 2 == 0 else -30))
    return prices


def test_low_volatility_stable_prices_yields_favorable_bias():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_STABLE", primary=FakePriceSource(_stable_prices()))
    report = ChiefRiskFundamentalsOfficer(manager, ticker="STABLE").analyze("Stable Asset")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH, Bias.NEUTRAL)
    assert report.risk_level in (RiskLevel.LOW, RiskLevel.MODERATE)
    assert len(report.factor_breakdown) == 2


def test_high_volatility_swinging_prices_yields_unfavorable_bias():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_VOLATILE", primary=FakePriceSource(_volatile_prices()))
    report = ChiefRiskFundamentalsOfficer(manager, ticker="VOLATILE").analyze("Volatile Asset")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert report.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)
    assert any("volatility" in r.lower() for r in report.risks)


def test_factor_breakdown_metadata_correct():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_STABLE", primary=FakePriceSource(_stable_prices()))
    report = ChiefRiskFundamentalsOfficer(manager, ticker="STABLE").analyze("Stable Asset")
    vol_factor = next(f for f in report.factor_breakdown if f.name == "Annualized Volatility")
    assert vol_factor.category == "Risk"
    assert vol_factor.source == "FAKE_YAHOO"
    assert vol_factor.forecast_value is None
    assert vol_factor.current_value is not None


def test_missing_data_yields_high_risk_zero_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    report = ChiefRiskFundamentalsOfficer(manager, ticker="NOTREGISTERED").analyze("Missing Asset")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.factor_breakdown == []
    assert report.is_degraded() is True


def test_insufficient_history_flagged_as_gap_not_crash():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_THIN", primary=FakePriceSource([100.0]))  # only 1 close
    report = ChiefRiskFundamentalsOfficer(manager, ticker="THIN").analyze("Thin History Asset")
    assert report.factor_breakdown == []
    assert any("insufficient history" in g.lower() for g in report.data_gaps)


def test_different_tickers_are_independent():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE_HISTORY_STABLE", primary=FakePriceSource(_stable_prices()))
    manager.register("PRICE_HISTORY_VOLATILE", primary=FakePriceSource(_volatile_prices()))
    stable_report = ChiefRiskFundamentalsOfficer(manager, ticker="STABLE").analyze("Stable")
    volatile_report = ChiefRiskFundamentalsOfficer(manager, ticker="VOLATILE").analyze("Volatile")
    assert stable_report.bias_score != volatile_report.bias_score
