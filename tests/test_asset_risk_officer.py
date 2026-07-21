from datetime import datetime, timezone

from agents.asset_risk_officer import ChiefAssetRiskOfficer
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import RiskLevel


class FakePriceHistorySource(DataSource):
    name = "FAKE_PRICE"
    default_ttl_seconds = 3600

    def __init__(self, rows_newest_first):
        self.rows = rows_newest_first

    def fetch(self, **kwargs):
        payload = {"ticker": "TEST", "latest_close": self.rows[0]["close"], "latest_date": self.rows[0]["date"], "history": self.rows}
        return payload, datetime.now(timezone.utc)


class FakeCotSource(DataSource):
    name = "FAKE_COT"
    default_ttl_seconds = 3600

    def __init__(self, noncomm_long, noncomm_short, comm_long, comm_short, open_interest, history=None):
        self.payload = {
            "noncomm_long": noncomm_long, "noncomm_short": noncomm_short,
            "comm_long": comm_long, "comm_short": comm_short, "open_interest": open_interest,
            "history": history or [
                {"noncomm_long": noncomm_long, "noncomm_short": noncomm_short, "comm_long": comm_long, "comm_short": comm_short},
            ],
        }

    def fetch(self, **kwargs):
        return self.payload, datetime.now(timezone.utc)


class FakeNewsSource(DataSource):
    name = "FAKE_NEWS"
    default_ttl_seconds = 3600

    def __init__(self, headlines):
        self.headlines = headlines

    def fetch(self, **kwargs):
        return {"headlines": self.headlines, "count": len(self.headlines)}, datetime.now(timezone.utc)


def _flat_price_rows(n=40, base=100.0):
    # newest-first, low volatility, no weekend gaps -> baseline "quiet" case
    from datetime import timedelta
    rows = []
    d = datetime(2026, 6, 1)
    for i in range(n):
        date = (d + timedelta(days=n - i)).date().isoformat()
        rows.append({"date": date, "close": base, "high": base + 0.5, "low": base - 0.5})
    return rows


def test_crowded_long_positioning_flags_elevated_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE", primary=FakePriceHistorySource(_flat_price_rows()))
    manager.register("COT", primary=FakeCotSource(noncomm_long=90000, noncomm_short=10000, comm_long=40000, comm_short=60000, open_interest=100000))

    officer = ChiefAssetRiskOfficer(manager, price_key="PRICE", cot_key="COT")
    report = officer.analyze("TEST")
    assert any("crowded long" in r.lower() for r in report.risks)
    assert report.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)


def test_event_risk_headlines_are_flagged():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE", primary=FakePriceHistorySource(_flat_price_rows()))
    manager.register("NEWS", primary=FakeNewsSource(["Fed decision looms as markets brace for volatility", "Local bakery wins award"]))

    officer = ChiefAssetRiskOfficer(manager, price_key="PRICE", news_key="NEWS")
    report = officer.analyze("TEST")
    assert any("event" in r.lower() or "catalyst" in r.lower() for r in report.risks)


def test_no_usable_data_defaults_to_high_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    # PRICE key required but never registered -> BaseAgent.analyze() logs a
    # gap and hands the agent zero usable datasets, same as a total outage.
    officer = ChiefAssetRiskOfficer(manager, price_key="PRICE")
    report = officer.analyze("TEST")
    assert report.risk_level == RiskLevel.HIGH


def test_asset_risk_officer_is_always_directionally_neutral():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("PRICE", primary=FakePriceHistorySource(_flat_price_rows()))
    officer = ChiefAssetRiskOfficer(manager, price_key="PRICE")
    report = officer.analyze("TEST")
    assert report.bias_score == 0.0
