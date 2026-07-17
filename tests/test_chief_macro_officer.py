from datetime import datetime, timezone

from agents.chief_macro_officer import ChiefMacroOfficer, KEY_CPI, KEY_UNRATE
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FredLikeSource(DataSource):
    """Returns a payload shaped exactly like FredConnector's output."""
    name = "FAKE_FRED"
    default_ttl_seconds = 300

    def __init__(self, history_values, latest_date="2026-06-01"):
        # history_values given oldest->newest; FredConnector returns newest-first
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


def _manager_with(cpi_values, unrate_values):
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(KEY_CPI, primary=FredLikeSource(cpi_values))
    manager.register(KEY_UNRATE, primary=FredLikeSource(unrate_values))
    return manager


def test_disinflation_and_improving_labor_market_is_bullish():
    # CPI falling (good), unemployment falling (good) -> bullish regime
    manager = _manager_with(cpi_values=[310, 305, 300], unrate_values=[4.5, 4.2, 4.0])
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.bias_score > 0
    assert report.data_gaps == []
    assert len(report.evidence) == 2


def test_reaccelerating_inflation_and_rising_unemployment_is_bearish():
    manager = _manager_with(cpi_values=[300, 310, 320], unrate_values=[4.0, 4.3, 4.6])
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert report.bias_score < 0
    assert any("re-accelerating" in r.lower() or "recession" in r.lower() for r in report.risks)


def test_missing_unemployment_data_reduces_confidence_and_flags_gap():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(KEY_CPI, primary=FredLikeSource([310, 305, 300]))
    # KEY_UNRATE never registered
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.is_degraded() is True
    assert any(KEY_UNRATE in gap for gap in report.data_gaps)
    assert report.confidence <= 60.0  # single-component confidence, per the scoring rule
