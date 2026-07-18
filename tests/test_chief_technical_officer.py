from datetime import datetime, timezone

from agents.chief_technical_officer import ChiefTechnicalOfficer
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
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
        payload = {
            "ticker": "TEST",
            "latest_close": newest_first[0],
            "latest_date": "day-0",
            "history": history,
        }
        return payload, datetime.now(timezone.utc)


def _manager_with(closes):
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE", primary=FakePriceHistorySource(closes))
    return manager


def test_sustained_uptrend_is_bullish():
    # 70 bars, gently and steadily rising -> uptrend + RSI above 50 + positive MACD
    closes = [100 + i * 0.3 for i in range(70)]
    manager = _manager_with(closes)
    report = ChiefTechnicalOfficer(manager, price_key="PRICE").analyze("TEST")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.data_gaps == []
    assert len(report.evidence) == 3  # RSI, MACD, trend all computed


def test_sustained_downtrend_is_bearish():
    closes = [170 - i * 0.3 for i in range(70)]
    manager = _manager_with(closes)
    report = ChiefTechnicalOfficer(manager, price_key="PRICE").analyze("TEST")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_overbought_rsi_flags_elevated_risk():
    # Strictly rising with no losses at all -> RSI = 100 (overbought)
    closes = [100 + i for i in range(70)]
    manager = _manager_with(closes)
    report = ChiefTechnicalOfficer(manager, price_key="PRICE").analyze("TEST")
    assert report.risk_level == RiskLevel.ELEVATED
    assert any("overbought" in r.lower() for r in report.risks)


def test_oversold_rsi_flags_elevated_risk():
    closes = [200 - i for i in range(70)]
    manager = _manager_with(closes)
    report = ChiefTechnicalOfficer(manager, price_key="PRICE").analyze("TEST")
    assert report.risk_level == RiskLevel.ELEVATED
    assert any("oversold" in r.lower() for r in report.risks)


def test_insufficient_history_yields_reduced_but_nonzero_confidence():
    # Enough for RSI(14) and a short trend read, but not MACD (needs 35 bars)
    closes = [100 + i * 0.5 for i in range(25)]
    manager = _manager_with(closes)
    report = ChiefTechnicalOfficer(manager, price_key="PRICE").analyze("TEST")
    assert report.confidence > 0
    assert report.confidence < 90.0  # not all 3 components available


def test_missing_price_data_yields_high_risk_zero_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    agent = ChiefTechnicalOfficer(manager, price_key="PRICE")
    report = agent.analyze("TEST")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True
