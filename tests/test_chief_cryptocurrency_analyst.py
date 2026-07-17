from datetime import datetime, timezone

from agents.chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FakeBinanceLikeSource(DataSource):
    """Returns a payload shaped exactly like BinanceFuturesConnector's output."""
    name = "FAKE_BINANCE"
    default_ttl_seconds = 30

    def __init__(self, funding_rate, oi_values_oldest_to_newest):
        self.funding_rate = funding_rate
        self.oi_values = oi_values_oldest_to_newest

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.oi_values))
        payload = {
            "symbol": "BTCUSDT",
            "latest_open_interest": newest_first[0],
            "latest_funding_rate": self.funding_rate,
            "history": [{"date": i, "open_interest": v} for i, v in enumerate(newest_first)],
        }
        return payload, datetime.now(timezone.utc)


def _manager_with(funding_rate, oi_values):
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("CRYPTO_BTC", primary=FakeBinanceLikeSource(funding_rate, oi_values))
    return manager


def test_positive_funding_and_rising_oi_is_bullish():
    manager = _manager_with(funding_rate=0.0003, oi_values=[1000, 1100, 1200])
    report = ChiefCryptocurrencyAnalyst(manager, crypto_key="CRYPTO_BTC").analyze("BTC")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence == 80.0  # both components present
    assert report.data_gaps == []


def test_negative_funding_and_falling_oi_is_bearish():
    manager = _manager_with(funding_rate=-0.0003, oi_values=[1200, 1100, 1000])
    report = ChiefCryptocurrencyAnalyst(manager, crypto_key="CRYPTO_BTC").analyze("BTC")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_extreme_positive_funding_elevates_risk():
    manager = _manager_with(funding_rate=0.002, oi_values=[1000, 1000, 1000])
    report = ChiefCryptocurrencyAnalyst(manager, crypto_key="CRYPTO_BTC").analyze("BTC")
    assert report.risk_level == RiskLevel.ELEVATED
    assert any("crowded long" in r.lower() for r in report.risks)


def test_extreme_negative_funding_elevates_risk():
    manager = _manager_with(funding_rate=-0.002, oi_values=[1000, 1000, 1000])
    report = ChiefCryptocurrencyAnalyst(manager, crypto_key="CRYPTO_BTC").analyze("BTC")
    assert report.risk_level == RiskLevel.ELEVATED
    assert any("crowded short" in r.lower() for r in report.risks)


def test_missing_crypto_data_yields_high_risk_zero_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    agent = ChiefCryptocurrencyAnalyst(manager, crypto_key="CRYPTO_ETH")
    report = agent.analyze("ETH")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True
