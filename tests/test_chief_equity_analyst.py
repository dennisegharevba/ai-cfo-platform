from datetime import datetime, timezone

from agents.chief_equity_analyst import ChiefEquityAnalyst
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias


class FakeEdgarLikeSource(DataSource):
    """Returns a payload shaped exactly like SecEdgarConnector's output."""
    name = "FAKE_EDGAR"
    default_ttl_seconds = 3600

    def __init__(self, values_oldest_to_newest):
        self.values = values_oldest_to_newest

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.values))
        payload = {
            "cik": "0000000000",
            "concept": "TEST",
            "latest_value": newest_first[0],
            "latest_date": "2026-06-30",
            "history": [{"value": v, "date": "2026-06-30", "form": "10-Q"} for v in newest_first],
        }
        return payload, datetime.now(timezone.utc)


def _manager_with(eps_values, revenue_values):
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("EPS_KEY", primary=FakeEdgarLikeSource(eps_values))
    manager.register("REV_KEY", primary=FakeEdgarLikeSource(revenue_values))
    return manager


def test_growing_eps_and_revenue_is_bullish():
    manager = _manager_with(eps_values=[1.00, 1.10, 1.25], revenue_values=[1000, 1100, 1250])
    report = ChiefEquityAnalyst(manager, eps_key="EPS_KEY", revenue_key="REV_KEY").analyze("AAPL")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.bias_score > 0
    assert report.data_gaps == []
    assert len(report.evidence) == 2


def test_shrinking_eps_and_revenue_is_bearish():
    manager = _manager_with(eps_values=[1.25, 1.10, 1.00], revenue_values=[1250, 1100, 1000])
    report = ChiefEquityAnalyst(manager, eps_key="EPS_KEY", revenue_key="REV_KEY").analyze("AAPL")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert report.bias_score < 0
    assert any("shrinking" in r.lower() or "contracting" in r.lower() for r in report.risks)


def test_missing_revenue_data_flags_gap_and_reduces_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("EPS_KEY", primary=FakeEdgarLikeSource([1.00, 1.10, 1.25]))
    # REV_KEY never registered
    report = ChiefEquityAnalyst(manager, eps_key="EPS_KEY", revenue_key="REV_KEY").analyze("AAPL")
    assert report.is_degraded() is True
    assert any("REV_KEY" in gap for gap in report.data_gaps)
    assert report.confidence <= 60.0


def test_independent_instances_for_different_tickers():
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("AAPL_EPS", primary=FakeEdgarLikeSource([1.00, 1.10, 1.25]))
    manager.register("AAPL_REV", primary=FakeEdgarLikeSource([1000, 1100, 1250]))
    manager.register("XYZ_EPS", primary=FakeEdgarLikeSource([1.25, 1.10, 1.00]))
    manager.register("XYZ_REV", primary=FakeEdgarLikeSource([1250, 1100, 1000]))

    aapl_report = ChiefEquityAnalyst(manager, eps_key="AAPL_EPS", revenue_key="AAPL_REV").analyze("AAPL")
    xyz_report = ChiefEquityAnalyst(manager, eps_key="XYZ_EPS", revenue_key="XYZ_REV").analyze("XYZ")
    assert aapl_report.bias_score > 0
    assert xyz_report.bias_score < 0
