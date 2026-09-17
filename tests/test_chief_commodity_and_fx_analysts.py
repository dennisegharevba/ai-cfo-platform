from datetime import datetime, timezone

from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_fx_analyst import ChiefFXAnalyst
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class FakeCotSource(DataSource):
    """Returns a payload shaped like the CotConnector's multi-week output."""
    name = "FAKE_COT"
    default_ttl_seconds = 300

    def __init__(self, weekly_rows, comm_rows=None):
        """
        weekly_rows: list of (noncomm_long, noncomm_short, open_interest),
            OLDEST FIRST (matches how the test scenarios below are written;
            reversed internally to match the connector's newest-first convention).
        comm_rows: optional list of (comm_long, comm_short), same length/order as
            weekly_rows — omit to simulate a payload with no commercial data at all.
        """
        self.weekly_rows = weekly_rows
        self.comm_rows = comm_rows

    def fetch(self, **kwargs):
        newest_first_rows = list(reversed(self.weekly_rows))
        comm_rows = list(reversed(self.comm_rows)) if self.comm_rows is not None else None

        history = []
        for i, (l, s, oi) in enumerate(newest_first_rows):
            row = {
                "report_date": f"2026-06-{i+1:02d}",
                "noncomm_long": str(l), "noncomm_short": str(s), "open_interest": str(oi),
            }
            if comm_rows is not None:
                cl, cs = comm_rows[i]
                row["comm_long"] = str(cl)
                row["comm_short"] = str(cs)
            history.append(row)

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
    # oldest -> newest: net 13000 -> 40000 (building)
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource([(95000, 82000, 480000), (120000, 80000, 500000)]))
    agent = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")
    report = agent.analyze("Gold")
    assert report.department == "Chief Commodity Analyst"
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.data_gaps == []
    assert not any("hedger" in e.lower() for e in report.evidence)  # never mentioned by default


def test_fx_analyst_bearish_on_reducing_length():
    # oldest -> newest: net 15000 -> -20000 (reducing/going short)
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_EUR_FX", primary=FakeCotSource([(100000, 85000, 480000), (80000, 100000, 500000)]))
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
    manager.register("COT_GOLD", primary=FakeCotSource([(95000, 82000, 480000), (120000, 80000, 500000)]))
    manager.register("COT_SILVER", primary=FakeCotSource([(100000, 85000, 480000), (80000, 100000, 500000)]))
    gold_agent = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD")
    silver_agent = ChiefCommodityAnalyst(manager, cot_key="COT_SILVER")
    gold_report = gold_agent.analyze("Gold")
    silver_report = silver_agent.analyze("Silver")
    assert gold_report.bias_score != silver_report.bias_score


def test_weekly_momentum_continuation_boosts_confidence():
    # oldest -> newest net: 10000, 25000, 20000, 22000, 24000
    # overall trend strongly bullish (10000 -> 24000); latest weekly move
    # (+2000) agrees with that direction; current (24000) is NOT the
    # window's max (25000 is), so this isolates "continuation" from "extreme".
    rows = [
        (10000, 0, 500000), (25000, 0, 500000), (20000, 0, 500000), (22000, 0, 500000), (24000, 0, 500000),
    ]
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource(rows))
    report = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD").analyze("Gold")
    assert report.confidence == 70.0  # 55 base + 15 continuation bonus, no extreme penalty
    assert any("confirms the broader" in c.lower() for c in report.catalysts)
    assert not any("extreme" in r.lower() for r in report.risks)


def test_weekly_momentum_reversal_watch_reduces_confidence_and_is_flagged():
    # oldest -> newest net: 10000, 24000, 20000, 22000, 18000
    # overall trend still bullish (10000 -> 18000), but the latest weekly
    # move (-4000) opposes that direction, and 18000 isn't the window's
    # extreme (24000 is), isolating "reversal_watch" from "extreme".
    rows = [
        (10000, 0, 500000), (24000, 0, 500000), (20000, 0, 500000), (22000, 0, 500000), (18000, 0, 500000),
    ]
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource(rows))
    report = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD").analyze("Gold")
    assert report.confidence == 40.0  # 55 base - 15 reversal penalty, no extreme penalty
    assert any("reversal signal" in r.lower() for r in report.risks)


def test_extreme_percentile_flagged_as_risk_and_reduces_confidence():
    # oldest -> newest net: 15000, 18000, 20000, 49000, 50000 — a fresh high,
    # but the latest weekly change (+1000) is small relative to the
    # position's size, isolating "extreme percentile" from any momentum signal.
    rows = [
        (15000, 0, 500000), (18000, 0, 500000), (20000, 0, 500000), (49000, 0, 500000), (50000, 0, 500000),
    ]
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource(rows))
    report = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD").analyze("Gold")
    assert report.confidence == 45.0  # 55 base - 10 extreme penalty, momentum "stable"
    assert any("extreme bullish reading" in r.lower() for r in report.risks)
    assert any("percentile" in e.lower() for e in report.evidence)


def test_percentile_evidence_clarifies_it_measures_something_different_from_the_trend_score():
    """
    Regression test for a real point of confusion caught via live
    testing: a live EUR/USD run showed a maxed-out -100.0 bias score
    (a genuine, severe multi-week reversal) alongside a percentile
    reading explicitly labeled "within a normal range" — both correct,
    but presented with nothing explaining why they don't contradict each
    other (the trend score measures the SIZE of the multi-week swing;
    the percentile measures where TODAY's position sits within its own
    recent range — two different questions). The percentile evidence line
    now explicitly says so, using the user's own real EUR/USD data
    (severe reversal: net +34,353 eight weeks ago -> net -58,091 today,
    yet the current reading isn't the window's single most extreme value).
    """
    # oldest -> newest, reproducing the real reported net positions
    rows = [
        (34353, 0, 700000), (30158, 0, 700000), (1099, 0, 700000), (-16227, 0, 700000),
        (-12605, 0, 700000), (-41338, 0, 700000), (-72447, 0, 700000), (-58091, 0, 700000),
    ]
    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_EUR_FX", primary=FakeCotSource(rows))
    report = ChiefFXAnalyst(manager, cot_key="COT_EUR_FX").analyze("EUR/USD")

    assert report.bias_score == -100.0  # the severe multi-week reversal is real
    percentile_line = next(e for e in report.evidence if "percentile" in e.lower())
    assert "separate question from the overall multi-week" in percentile_line
    assert "can genuinely disagree" in percentile_line


def test_commercial_data_never_shown_by_default(monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "ENABLE_COMMERCIAL_POSITIONING_DISPLAY", False)
    import agents.positioning_agent_base as pab
    monkeypatch.setattr(pab, "ENABLE_COMMERCIAL_POSITIONING_DISPLAY", False)

    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register("COT_GOLD", primary=FakeCotSource(
        [(95000, 82000, 480000), (120000, 80000, 500000)],
        comm_rows=[(70000, 65000), (90000, 60000)],
    ))
    report = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD").analyze("Gold")
    assert not any("hedger" in e.lower() for e in report.evidence)


def test_commercial_data_shown_when_enabled_but_never_affects_bias_or_confidence(monkeypatch):
    import agents.positioning_agent_base as pab

    rows = [(95000, 82000, 480000), (120000, 80000, 500000)]

    # Same speculative data, but wildly different (even contradicting) commercial
    # data across two runs — bias_score and confidence must be IDENTICAL either way.
    monkeypatch.setattr(pab, "ENABLE_COMMERCIAL_POSITIONING_DISPLAY", True)

    manager_a = DataIntegrityManager(min_quality_threshold=50)
    manager_a.register("COT_GOLD", primary=FakeCotSource(rows, comm_rows=[(90000, 60000), (70000, 65000)]))
    report_a = ChiefCommodityAnalyst(manager_a, cot_key="COT_GOLD").analyze("Gold")

    manager_b = DataIntegrityManager(min_quality_threshold=50)
    manager_b.register("COT_GOLD", primary=FakeCotSource(rows, comm_rows=[(60000, 90000), (65000, 70000)]))
    report_b = ChiefCommodityAnalyst(manager_b, cot_key="COT_GOLD").analyze("Gold")

    assert report_a.bias_score == report_b.bias_score
    assert report_a.confidence == report_b.confidence
    assert any("informational only" in e.lower() for e in report_a.evidence)
    assert any("informational only" in e.lower() for e in report_b.evidence)
