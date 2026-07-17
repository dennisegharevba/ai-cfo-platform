from datetime import datetime, timezone

from agents.chief_bond_strategist import ChiefBondStrategist, KEY_DGS10, KEY_DGS2
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FredLikeSource(DataSource):
    name = "FAKE_FRED"
    default_ttl_seconds = 300

    def __init__(self, history_values, latest_date="2026-06-01"):
        self.history_values = history_values
        self.latest_date = latest_date

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.history_values))
        payload = {
            "series_id": "TEST",
            "latest_value": str(newest_first[0]),
            "latest_date": self.latest_date,
            "history": [{"value": str(v), "date": self.latest_date} for v in newest_first],
        }
        return payload, datetime.now(timezone.utc)


def _manager_with(dgs10_values, dgs2_values):
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(KEY_DGS10, primary=FredLikeSource(dgs10_values))
    manager.register(KEY_DGS2, primary=FredLikeSource(dgs2_values))
    return manager


def test_falling_yields_are_bullish_for_bond_prices():
    manager = _manager_with(dgs10_values=[4.5, 4.3, 4.0], dgs2_values=[4.6, 4.5, 4.4])
    report = ChiefBondStrategist(manager).analyze("US Treasuries")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.bias_score > 0


def test_rising_yields_are_bearish_for_bond_prices():
    manager = _manager_with(dgs10_values=[4.0, 4.3, 4.6], dgs2_values=[4.0, 4.1, 4.2])
    report = ChiefBondStrategist(manager).analyze("US Treasuries")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert report.bias_score < 0


def test_inverted_yield_curve_flags_high_risk():
    # 10Y ends at 4.0, 2Y ends at 4.5 -> inverted (spread -0.5)
    manager = _manager_with(dgs10_values=[4.2, 4.1, 4.0], dgs2_values=[4.3, 4.4, 4.5])
    report = ChiefBondStrategist(manager).analyze("US Treasuries")
    assert report.risk_level == RiskLevel.HIGH
    assert any("invert" in r.lower() for r in report.risks)


def test_normal_positive_curve_is_not_high_risk():
    manager = _manager_with(dgs10_values=[4.5, 4.5, 4.5], dgs2_values=[3.5, 3.5, 3.5])
    report = ChiefBondStrategist(manager).analyze("US Treasuries")
    assert report.risk_level != RiskLevel.HIGH


def test_missing_2y_data_still_produces_price_bias_but_degrades_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(KEY_DGS10, primary=FredLikeSource([4.5, 4.3, 4.0]))
    report = ChiefBondStrategist(manager).analyze("US Treasuries")
    assert report.is_degraded() is True
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)  # 10Y alone still scores
