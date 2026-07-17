from datetime import datetime, timezone

from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_fx_analyst import ChiefFXAnalyst
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FakeCotSource(DataSource):
    """Returns a payload shaped like the Phase 3 CotConnector's multi-week output."""
    name = "FAKE_COT"
    default_ttl_seconds = 300

    def __init__(self, weekly_rows):
        """weekly_rows: list of (noncomm_long, noncomm_short, open_interest), newest first."""
        self.weekly_rows = weekly_rows

    def fetch(self, **kwargs):
        history = [
            {
                "report_date": f"2026-06-{i+1:02d}",
                "noncomm_long": str(l), "noncomm_short": str(s), "open_interest": str(oi),
            }
            for i, (l, s, oi) in enumerate(self.weekly_rows)
        ]
        payload = {
            "market": "TEST MARKET",
            "report_date": history[0]["report_date"],
            "noncomm_long": history[0]["noncomm_long"],
            "noncomm_short": history[0]["noncomm_short"],
            "open_interest": history[0]["open_interest"],
            "history": history,
        }
        return payload, datetime.now(timezone.utc)

    def validate_shape(self, payload):
        return isinstance(payload, dict) and len(payload.get("history", [])) > 0


def test_commodity_analyst_bullish_on_building_length():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource([(120000, 80000, 500000), (95000, 82000, 480000)]))
    agent = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")
    report = agent.analyze("Gold")
    assert report.department == "Chief Commodity Analyst"
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence == 70.0
    assert report.data_gaps == []


def test_fx_analyst_bearish_on_reducing_length():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_EUR_FX", primary=FakeCotSource([(80000, 100000, 500000), (100000, 85000, 480000)]))
    agent = ChiefFXAnalyst(manager, cot_key="COT_EUR_FX")
    report = agent.analyze("EUR/USD")
    assert report.department == "Chief FX Analyst"
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_crowded_long_elevates_risk_regardless_of_bias_direction():
    manager = DataIntegrityManager(min_quality_threshold=50)
    # extreme long positioning (300k/50k on 500k OI = 50% net long) but flat trend
    manager.register("COT_GOLD", primary=FakeCotSource([(300000, 50000, 500000), (300000, 50000, 500000)]))
    agent = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")
    report = agent.analyze("Gold")
    assert report.risk_level == RiskLevel.ELEVATED
    assert any("crowded long" in r.lower() for r in report.risks)


def test_missing_cot_data_yields_high_risk_zero_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    # COT_SILVER never registered
    agent = ChiefCommodityAnalyst(manager, cot_key="COT_SILVER")
    report = agent.analyze("Silver")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True
    assert any("COT_SILVER" in gap for gap in report.data_gaps)


def test_different_agent_instances_use_independent_cot_keys():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource([(120000, 80000, 500000), (95000, 82000, 480000)]))
    manager.register("COT_SILVER", primary=FakeCotSource([(80000, 100000, 500000), (100000, 85000, 480000)]))
    gold_agent = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")
    silver_agent = ChiefCommodityAnalyst(manager, cot_key="COT_SILVER")
    gold_report = gold_agent.analyze("Gold")
    silver_report = silver_agent.analyze("Silver")
    assert gold_report.bias_score != silver_report.bias_score
