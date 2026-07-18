from datetime import datetime, timezone

from agents.chief_sentiment_officer import ChiefSentimentOfficer
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FakeNewsSource(DataSource):
    name = "FAKE_NEWS"
    default_ttl_seconds = 60

    def __init__(self, headlines):
        self.headlines = headlines

    def fetch(self, **kwargs):
        payload = {"feed_url": "fake", "headlines": self.headlines, "count": len(self.headlines)}
        return payload, datetime.now(timezone.utc)


class FakeCotSource(DataSource):
    name = "FAKE_COT"
    default_ttl_seconds = 300

    def __init__(self, weekly_rows):
        self.weekly_rows = weekly_rows  # list of (long, short, oi), newest first order desired

    def fetch(self, **kwargs):
        history = [
            {"report_date": f"2026-06-{i+1:02d}", "noncomm_long": str(l), "noncomm_short": str(s), "open_interest": str(oi)}
            for i, (l, s, oi) in enumerate(self.weekly_rows)
        ]
        payload = {
            "market": "TEST", "report_date": history[0]["report_date"],
            "noncomm_long": history[0]["noncomm_long"], "noncomm_short": history[0]["noncomm_short"],
            "open_interest": history[0]["open_interest"], "history": history,
        }
        return payload, datetime.now(timezone.utc)


def test_bullish_news_only_gives_bullish_bias():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource([
        "Stocks rally to record high", "Markets surge on strong earnings",
    ]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS").analyze("Market Sentiment")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence == 55.0  # 30 base + 25 for one component


def test_bearish_news_only_gives_bearish_bias():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource([
        "Markets plunge on recession fears", "Tech selloff deepens",
    ]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS").analyze("Market Sentiment")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_news_plus_cot_blend_both_components():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource(["Stocks rally to record high"]))
    manager.register("COT_GOLD", primary=FakeCotSource([(120000, 80000, 500000), (95000, 82000, 480000)]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS", cot_key="COT_GOLD").analyze("Gold Sentiment")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence == 80.0  # 30 + 25*2 components
    assert len(report.evidence) == 2


def test_crowded_cot_positioning_elevates_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource(["Markets steady today"]))
    manager.register("COT_GOLD", primary=FakeCotSource([(300000, 50000, 500000), (300000, 50000, 500000)]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS", cot_key="COT_GOLD").analyze("Gold Sentiment")
    assert report.risk_level == RiskLevel.ELEVATED
    assert any("crowded long" in r.lower() for r in report.risks)


def test_missing_news_data_yields_high_risk_zero_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    agent = ChiefSentimentOfficer(manager, news_key="NEWS")
    report = agent.analyze("Market Sentiment")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True


def test_missing_optional_cot_still_produces_news_only_report():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource(["Stocks rally to record high"]))
    # COT_GOLD never registered
    report = ChiefSentimentOfficer(manager, news_key="NEWS", cot_key="COT_GOLD").analyze("Gold Sentiment")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.is_degraded() is True
    assert any("COT_GOLD" in gap for gap in report.data_gaps)
