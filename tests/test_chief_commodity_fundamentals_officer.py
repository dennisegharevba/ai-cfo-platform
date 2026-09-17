from datetime import datetime, timezone

from agents.chief_commodity_fundamentals_officer import (
    ChiefCommodityFundamentalsOfficer, _dataset_key,
)
from core.data_source import DataSource
from core.refresh_manager import DataIntegrityManager
from models.report import Bias, RiskLevel


class EiaLikeSource(DataSource):
    """Returns a payload shaped exactly like EiaConnector's output."""
    name = "FAKE_EIA"
    default_ttl_seconds = 3600

    def __init__(self, history_values, latest_date="2026-06-15"):
        # oldest -> newest; EiaConnector returns newest-first
        self.history_values = history_values
        self.latest_date = latest_date

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.history_values))
        payload = {
            "route": "test/route",
            "latest_value": newest_first[0],
            "latest_date": self.latest_date,
            "history": [{"value": v, "date": self.latest_date} for v in newest_first],
        }
        return payload, datetime.now(timezone.utc)


def test_falling_crude_inventories_is_bullish():
    manager = DataIntegrityManager(min_quality_threshold=50)
    key = _dataset_key("Crude Oil", "crude_oil_inventories")
    manager.register(key, primary=EiaLikeSource([450, 430, 410]))  # falling stocks -> bullish
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Crude Oil").analyze("Crude Oil")
    assert report.department == "Chief Commodity Fundamentals Officer"
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.data_gaps == []
    assert len(report.factor_breakdown) == 1


def test_rising_natural_gas_storage_is_bearish():
    manager = DataIntegrityManager(min_quality_threshold=50)
    key = _dataset_key("Natural Gas", "natural_gas_storage")
    manager.register(key, primary=EiaLikeSource([3000, 3200, 3400]))  # rising storage -> bearish
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Natural Gas").analyze("Natural Gas")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert any("headwind" in r.lower() for r in report.risks)


def test_gold_catalysts_and_risks_are_real_narrative_not_score_labels():
    """
    Update, 2026-09-17: direct fix for the user's screenshot complaint —
    Gold's Trade Decision Engine showed "Federal Funds Rate is a headwind
    (score -X.X)" with no real number or explanation, "still stuck to COT
    reports" with no real fundamental interpretation. Confirms Gold's own
    USD-fundamentals factors (real yield, dollar index, fed funds) now
    carry a real, gold-specific explanation.
    """
    manager = DataIntegrityManager(min_quality_threshold=50)
    from agents.chief_macro_officer import KEY_REAL_YIELD, KEY_DOLLAR_INDEX, KEY_FED_FUNDS
    manager.register(KEY_REAL_YIELD, primary=EiaLikeSource([1.0, 1.5, 2.0]))  # rising real yield -> bearish for gold
    manager.register(KEY_DOLLAR_INDEX, primary=EiaLikeSource([100, 105, 110]))
    manager.register(KEY_FED_FUNDS, primary=EiaLikeSource([4.0, 4.5, 5.0]))

    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Gold").analyze("Gold")

    assert report.risks, "expected at least one risk line with all factors bearish for gold"
    for r in report.risks:
        assert "is a headwind (score" not in r
        assert "is supportive (score" not in r
    assert any("gold" in r.lower() for r in report.risks)  # real, asset-specific reasoning


def test_unconfigured_commodity_yields_honest_neutral_result_no_fabrication():
    # Copper has no factors configured at all — the honest, correct
    # behavior per the module's documented scope, not a bug.
    manager = DataIntegrityManager(min_quality_threshold=50)
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Copper").analyze("Copper")
    assert report.bias == Bias.NEUTRAL
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.factor_breakdown == []
    assert any("no free" in g.lower() for g in report.data_gaps)


def test_missing_data_for_configured_commodity_is_a_real_gap():
    manager = DataIntegrityManager(min_quality_threshold=50)
    # Crude Oil IS configured, but its data source was never registered
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Crude Oil").analyze("Crude Oil")
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.is_degraded() is True


def test_different_commodity_instances_are_independent():
    manager = DataIntegrityManager(min_quality_threshold=50)
    crude_key = _dataset_key("Crude Oil", "crude_oil_inventories")
    gas_key = _dataset_key("Natural Gas", "natural_gas_storage")
    manager.register(crude_key, primary=EiaLikeSource([450, 430, 410]))
    manager.register(gas_key, primary=EiaLikeSource([3000, 3200, 3400]))

    crude_report = ChiefCommodityFundamentalsOfficer(manager, commodity="Crude Oil").analyze("Crude Oil")
    gas_report = ChiefCommodityFundamentalsOfficer(manager, commodity="Natural Gas").analyze("Natural Gas")
    assert crude_report.bias_score != gas_report.bias_score
    assert crude_report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert gas_report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_factor_breakdown_metadata_correct():
    manager = DataIntegrityManager(min_quality_threshold=50)
    key = _dataset_key("Crude Oil", "crude_oil_inventories")
    manager.register(key, primary=EiaLikeSource([450, 430, 410]))
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Crude Oil").analyze("Crude Oil")
    factor = report.factor_breakdown[0]
    assert factor.source == "FAKE_EIA"
    assert factor.category == "Commodity Fundamentals"
    assert factor.forecast_value is None
    assert factor.importance_weight == 7.0


def test_wti_crude_oil_alias_resolves_to_the_same_factors_as_crude_oil():
    """
    config/cftc_markets.py's naming convention for this commodity is 'WTI
    Crude Oil' (matching CFTC's own report language), while this module's
    own tests/demo/dashboard code use the shorter 'Crude Oil'. Both names
    must resolve to the identical configured factor list — this was a real
    mismatch caught while wiring config/watchlist.py (which uses the CFTC
    convention) and fixed by aliasing rather than renaming either existing
    caller's convention.
    """
    from agents.chief_commodity_fundamentals_officer import COMMODITY_FACTOR_SPECS, EIA_ROUTE_SPECS

    assert COMMODITY_FACTOR_SPECS["WTI Crude Oil"] == COMMODITY_FACTOR_SPECS["Crude Oil"]
    assert EIA_ROUTE_SPECS[("WTI Crude Oil", "crude_oil_inventories")] == EIA_ROUTE_SPECS[("Crude Oil", "crude_oil_inventories")]

    manager = DataIntegrityManager(min_quality_threshold=50)
    key = _dataset_key("WTI Crude Oil", "crude_oil_inventories")
    manager.register(key, primary=EiaLikeSource([450, 430, 410]))
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="WTI Crude Oil").analyze("WTI Crude Oil")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert len(report.factor_breakdown) == 1


def test_register_commodity_fundamentals_sources_works_with_wti_alias():
    from agents.chief_commodity_fundamentals_officer import register_commodity_fundamentals_sources

    manager = DataIntegrityManager(min_quality_threshold=50)
    register_commodity_fundamentals_sources(manager, "WTI Crude Oil", eia_api_key="test_key")
    key = _dataset_key("WTI Crude Oil", "crude_oil_inventories")
    assert manager.is_registered(key) is True


# --- Precious metals: fundamentally backed by USD fundamentals ---

def test_gold_falling_real_yield_dollar_and_fed_funds_is_bullish():
    from agents.chief_macro_officer import KEY_REAL_YIELD, KEY_DOLLAR_INDEX, KEY_FED_FUNDS

    manager = DataIntegrityManager(min_quality_threshold=50)
    # All three USD fundamentals falling -> bullish for Gold (lower real
    # yields, weaker dollar, easier Fed policy all support gold prices).
    manager.register(KEY_REAL_YIELD, primary=EiaLikeSource([2.5, 2.0, 1.5]))
    manager.register(KEY_DOLLAR_INDEX, primary=EiaLikeSource([105, 102, 99]))
    manager.register(KEY_FED_FUNDS, primary=EiaLikeSource([5.5, 5.25, 5.0]))
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Gold").analyze("Gold")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert len(report.factor_breakdown) == 3
    assert report.data_gaps == []


def test_gold_rising_real_yield_dollar_and_fed_funds_is_bearish():
    from agents.chief_macro_officer import KEY_REAL_YIELD, KEY_DOLLAR_INDEX, KEY_FED_FUNDS

    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(KEY_REAL_YIELD, primary=EiaLikeSource([1.5, 2.0, 2.5]))
    manager.register(KEY_DOLLAR_INDEX, primary=EiaLikeSource([99, 102, 105]))
    manager.register(KEY_FED_FUNDS, primary=EiaLikeSource([5.0, 5.25, 5.5]))
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Gold").analyze("Gold")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)


def test_gold_reuses_chief_macro_officers_exact_dataset_keys():
    """
    The whole point of the override_key design: Gold's USD factors must
    read from the SAME DataIntegrityManager keys Chief Macro Officer
    registers, not a separate Gold-namespaced copy — proving one fetch
    genuinely serves both departments rather than silently duplicating it.
    """
    from agents.chief_macro_officer import (
        register_macro_data_sources, KEY_REAL_YIELD, KEY_DOLLAR_INDEX, KEY_FED_FUNDS,
    )
    from connectors.fred_connector import FredConnector

    manager = DataIntegrityManager(min_quality_threshold=50)
    register_macro_data_sources(manager, fred_api_key="")  # registers real FredConnectors under the shared keys

    # Confirm Gold's own required keys are EXACTLY those same 3 keys —
    # not a Gold-specific alternative.
    gold_agent = ChiefCommodityFundamentalsOfficer(manager, commodity="Gold")
    assert set(gold_agent.required_dataset_keys()) == {KEY_REAL_YIELD, KEY_DOLLAR_INDEX, KEY_FED_FUNDS}
    for key in gold_agent.required_dataset_keys():
        assert manager.is_registered(key)


def test_silver_platinum_palladium_share_golds_factor_list():
    from agents.chief_commodity_fundamentals_officer import COMMODITY_FACTOR_SPECS

    for metal in ("Silver", "Platinum", "Palladium"):
        assert COMMODITY_FACTOR_SPECS[metal] == COMMODITY_FACTOR_SPECS["Gold"]


def test_register_commodity_fundamentals_sources_is_a_noop_for_gold():
    """
    Gold's factors all use override_key (shared with Chief Macro Officer),
    so register_commodity_fundamentals_sources() — which only knows how to
    register EIA connectors — must skip them entirely rather than trying
    (and failing) to build an EIA connector for a FRED series.
    """
    from agents.chief_commodity_fundamentals_officer import register_commodity_fundamentals_sources

    manager = DataIntegrityManager(min_quality_threshold=50)
    register_commodity_fundamentals_sources(manager, "Gold", eia_api_key="test_key")
    # Nothing should have been registered — Gold's keys are Macro's to register.
    assert len(manager._registrations) == 0


def test_gold_factor_metadata_reflects_shared_source():
    from agents.chief_macro_officer import KEY_REAL_YIELD

    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(KEY_REAL_YIELD, primary=EiaLikeSource([2.5, 2.0, 1.5]))
    report = ChiefCommodityFundamentalsOfficer(manager, commodity="Gold").analyze("Gold")
    real_yield_factor = next(f for f in report.factor_breakdown if "Real Yield" in f.name)
    assert real_yield_factor.category == "Commodity Fundamentals"
    assert real_yield_factor.importance_weight == 8.0
    assert real_yield_factor.forecast_value is None


def test_recalibrated_eia_normalization_stops_moderate_seasonal_moves_from_clamping():
    """
    Regression test for a real issue caught via live testing: with the
    EIA_API_KEY working, a live run of Crude Oil Inventories clamped at
    the exact +100.0 extreme — the same over-clamping signature already
    found and fixed for several Chief Macro Officer factors (see
    docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md). Crude oil and
    especially natural gas inventories are known to swing significantly
    due to well-documented seasonal patterns over a 12-week window,
    making a tight 5% threshold prone to near-constant clamping regardless
    of whether current conditions are actually unusual. Proven directly:
    an 8% seasonal-scale inventory decline no longer clamps either
    commodity's recalibrated factor.
    """
    eight_pct_decline = [100.0, 97.0, 94.0, 92.0]  # oldest -> newest, an 8% decline

    manager = DataIntegrityManager(min_quality_threshold=50)
    manager.register(_dataset_key("Crude Oil", "crude_oil_inventories"), primary=EiaLikeSource(eight_pct_decline))
    crude_report = ChiefCommodityFundamentalsOfficer(manager, commodity="Crude Oil").analyze("Crude Oil")
    crude_factor = crude_report.factor_breakdown[0]
    assert abs(crude_factor.score) < 100.0

    manager2 = DataIntegrityManager(min_quality_threshold=50)
    manager2.register(_dataset_key("Natural Gas", "natural_gas_storage"), primary=EiaLikeSource(eight_pct_decline))
    gas_report = ChiefCommodityFundamentalsOfficer(manager2, commodity="Natural Gas").analyze("Natural Gas")
    gas_factor = gas_report.factor_breakdown[0]
    assert abs(gas_factor.score) < 100.0
    # Natural Gas was widened further than Crude Oil (20.0 vs 10.0) — the
    # same input should therefore score CLOSER to neutral for gas.
    assert abs(gas_factor.score) < abs(crude_factor.score)
