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


def test_bullish_news_only_gives_bullish_bias():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource([
        "Stocks rally to record high", "Markets surge on strong earnings",
    ]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS").analyze("Market Sentiment")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence == 55.0


def test_bearish_news_only_gives_bearish_bias():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource([
        "Markets plunge on recession fears", "Tech selloff deepens",
    ]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS").analyze("Market Sentiment")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_missing_news_data_yields_high_risk_zero_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    agent = ChiefSentimentOfficer(manager, news_key="NEWS")
    report = agent.analyze("Market Sentiment")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True


def test_no_cot_parameter_accepted_anymore():
    """
    Regression test for the deliberate restructuring (see
    docs/ARCHITECTURE_POSITIONING_SEPARATION.md): Chief Sentiment Officer
    no longer accepts a cot_key at all — institutional (COT) positioning
    is exclusively Chief Commodity/FX Analyst's job now, never re-blended
    into a second "sentiment" score under a different name.
    """
    manager = DataIntegrityManager(min_quality_threshold=50)
    try:
        ChiefSentimentOfficer(manager, news_key="NEWS", cot_key="COT_GOLD")
        assert False, "cot_key should no longer be an accepted parameter"
    except TypeError:
        pass


def test_factor_breakdown_populated_for_news_only():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("MARKET_NEWS", primary=FakeNewsSource(
        ["Stocks surge on strong earnings", "Markets rally as growth beats expectations"]
    ))
    report = ChiefSentimentOfficer(manager, news_key="MARKET_NEWS").analyze("Broad Market")
    assert len(report.factor_breakdown) == 1
    factor = report.factor_breakdown[0]
    assert factor.name == "News Headline Sentiment"
    assert factor.category == "Sentiment"
    assert factor.forecast_value is None


def test_factor_breakdown_never_includes_a_positioning_factor():
    """Since the COT blend was removed entirely, factor_breakdown should
    never contain anything but the News Headline Sentiment factor —
    positioning data belongs to Chief Commodity/FX Analyst exclusively now."""
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("NEWS", primary=FakeNewsSource(["Stocks rally to record high"]))
    report = ChiefSentimentOfficer(manager, news_key="NEWS").analyze("Gold Sentiment")
    names = {f.name for f in report.factor_breakdown}
    assert "Speculative Positioning (Crowd Sentiment)" not in names


def test_factor_breakdown_empty_when_no_data():
    manager = DataIntegrityManager(min_quality_threshold=50)
    report = ChiefSentimentOfficer(manager, news_key="MARKET_NEWS").analyze("Broad Market")
    assert report.factor_breakdown == []
