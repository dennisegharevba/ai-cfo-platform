from datetime import datetime, timedelta, timezone

from unittest.mock import patch

from agents.chief_macro_officer import (
    ChiefMacroOfficer, _FACTOR_SPECS, KEY_FED_FUNDS, KEY_REAL_YIELD, KEY_VIX, KEY_DGS10_FOR_REGIME,
    _FRED_SERIES_IDS, register_macro_data_sources,
)
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


class FredLikeSourceWithDates(DataSource):
    """
    Like FredLikeSource, but with REAL distinct per-entry dates — needed
    for the regime filters that compare a value against its reading N
    days ago (agents.chief_macro_officer._value_n_days_ago requires
    actual distinct dates to find a match, unlike the plain trend-score
    factors which only compare the oldest vs. newest entry regardless of date).
    """
    name = "FAKE_FRED"
    default_ttl_seconds = 300

    def __init__(self, dated_values):
        """dated_values: list of (value, "YYYY-MM-DD") tuples, oldest first."""
        self.dated_values = dated_values

    def fetch(self, **kwargs):
        newest_first = list(reversed(self.dated_values))
        payload = {
            "series_id": "TEST",
            "latest_value": str(newest_first[0][0]),
            "latest_date": newest_first[0][1],
            "history": [{"value": str(v), "date": d} for v, d in newest_first],
        }
        return payload, datetime.now(timezone.utc)


def _dated_series(latest_date_str: str, latest_value: float, days_back: int, past_value: float) -> FredLikeSourceWithDates:
    """A simple two-point dated series: `past_value` at (latest_date - days_back), `latest_value` at latest_date."""
    latest = datetime.strptime(latest_date_str, "%Y-%m-%d")
    past = latest - timedelta(days=days_back)
    return FredLikeSourceWithDates([(past_value, past.strftime("%Y-%m-%d")), (latest_value, latest_date_str)])


def _register_regime_sources(manager, fed_funds_falling=True, real_yield_falling=True, treasury_falling=True, vix_level=18.0):
    """Register all 4 Institutional Market Regime keys with dated series so
    both the trend AND the N-days-ago bps comparisons can actually compute."""
    manager.register(
        KEY_FED_FUNDS,
        primary=FredLikeSource([5.5, 5.25, 5.0] if fed_funds_falling else [5.0, 5.25, 5.5], latest_date="2026-06-01"),
    )
    manager.register(
        KEY_REAL_YIELD,
        primary=_dated_series("2026-06-01", 1.5 if real_yield_falling else 2.0, 30, 2.0 if real_yield_falling else 1.5),
    )
    manager.register(
        KEY_DGS10_FOR_REGIME,
        primary=_dated_series("2026-06-01", 4.0 if treasury_falling else 4.5, 7, 4.5 if treasury_falling else 4.0),
    )
    manager.register(KEY_VIX, primary=FredLikeSource([vix_level, vix_level, vix_level], latest_date="2026-06-01"))


def _register_all_factors(manager, direction="bullish"):
    """Register every factor key with a trend matching `direction`, respecting
    each factor's own lower_is_bullish flag so the OVERALL regime reads as
    intended (e.g. for 'bullish', unemployment/CPI/claims should FALL while
    GDP/payrolls/confidence should RISE)."""
    for _, key, lower_is_bullish, _, _ in _FACTOR_SPECS:
        if direction == "bullish":
            values = [100, 90, 80] if lower_is_bullish else [80, 90, 100]
        else:
            values = [80, 90, 100] if lower_is_bullish else [100, 90, 80]
        manager.register(key, primary=FredLikeSource(values))


def test_all_factors_bullish_gives_bullish_high_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.bias_score > 0
    assert report.data_gaps == []
    assert len(report.factor_breakdown) == len(_FACTOR_SPECS)
    assert report.confidence > 0


def test_all_factors_bearish_gives_bearish():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bearish")
    _register_regime_sources(manager)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.bias in (Bias.BEARISH, Bias.STRONGLY_BEARISH)
    assert report.bias_score < 0
    assert any("headwind" in r.lower() for r in report.risks)


def test_factor_breakdown_has_correct_metadata():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    cpi_factor = next(f for f in report.factor_breakdown if "CPI (Headline" in f.name)
    assert cpi_factor.source == "FAKE_FRED"
    assert cpi_factor.current_value is not None
    assert cpi_factor.previous_value is not None
    assert cpi_factor.forecast_value is None  # honestly unavailable, never fabricated
    assert cpi_factor.importance_weight == 8.0
    assert cpi_factor.confidence > 0


def test_missing_most_factors_flags_gaps_and_elevates_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    # Register only 2 of 16 factors
    manager.register("FRED_CPI", primary=FredLikeSource([100, 90, 80]))
    manager.register("FRED_UNRATE", primary=FredLikeSource([100, 90, 80]))
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.is_degraded() is True
    assert len(report.factor_breakdown) == 2
    assert report.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)
    assert any("incomplete" in r.lower() for r in report.risks)


def test_no_data_at_all_yields_neutral_zero_confidence_high_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.bias == Bias.NEUTRAL
    assert report.confidence == 0.0
    assert report.risk_level == RiskLevel.HIGH
    assert report.factor_breakdown == []
    assert report.is_degraded() is True
    # Even with zero macro factors, the regime object itself is always
    # attached (never None) — just reflecting "nothing available."
    assert report.market_regime is not None
    assert report.market_regime.combined_score == 0.0


def test_evidence_lines_include_factors_and_regime_summary():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    # 16 factor lines + 1 regime summary line + 6 market-impact lines
    assert len(report.evidence) > len(_FACTOR_SPECS)
    assert any("Core PCE" in e for e in report.evidence)
    assert any("Institutional Market Regime" in e for e in report.evidence)
    assert any("Market impact" in e for e in report.evidence)


def test_disagreeing_factors_produce_moderate_or_elevated_risk_not_high():
    # Half the factors bullish, half bearish -> real disagreement, but with
    # ALL 16 factors present this should not fall back to the "missing data"
    # HIGH risk path.
    manager = DataIntegrityManager(min_quality_threshold=50)
    for i, (_, key, lower_is_bullish, _, _) in enumerate(_FACTOR_SPECS):
        bullish = (i % 2 == 0)
        if bullish:
            values = [100, 90, 80] if lower_is_bullish else [80, 90, 100]
        else:
            values = [80, 90, 100] if lower_is_bullish else [100, 90, 80]
        manager.register(key, primary=FredLikeSource(values))
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert report.risk_level in (RiskLevel.MODERATE, RiskLevel.ELEVATED)
    assert len(report.factor_breakdown) == len(_FACTOR_SPECS)


# --- Institutional Market Regime integration ---

def test_regime_confirming_macro_boosts_confidence():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager, fed_funds_falling=True, real_yield_falling=True, treasury_falling=True, vix_level=12.0)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    # Regime should agree with the bullish macro bias here (falling rates,
    # falling real yields, falling treasury yields, low VIX are all bullish).
    assert report.market_regime.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH)
    assert report.confidence >= 90.0  # base confidence + full-alignment boost, clamped at 100


def test_regime_conflicting_with_macro_reduces_confidence():
    # Deliberately MODERATE (not maximally saturated) macro factors: with
    # macro saturated at +/-100, the regime's 60% combined weight
    # mathematically CANNOT flip the sign even at every component's most
    # extreme bearish reading (0.4*100=40 always exceeds the worst-case
    # -35.25 the other components can contribute) — so a moderate reading
    # is what actually lets this test exercise a genuine conflict.
    def _register_moderate_factors(manager):
        for _, key, lower_is_bullish, _, _ in _FACTOR_SPECS:
            values = [100, 97] if lower_is_bullish else [97, 100]
            manager.register(key, primary=FredLikeSource(values))

    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_moderate_factors(manager)
    # Regime inputs all point maximally bearish (rising rates/yields, high
    # VIX) while the moderate Macro factors above are bullish -> genuine conflict.
    _register_regime_sources(manager, fed_funds_falling=False, real_yield_falling=False, treasury_falling=False, vix_level=32.0)
    report_conflicting = ChiefMacroOfficer(manager).analyze("US Macro Outlook")

    manager_agree = DataIntegrityManager(min_quality_threshold=50)
    _register_moderate_factors(manager_agree)
    _register_regime_sources(manager_agree, fed_funds_falling=True, real_yield_falling=True, treasury_falling=True, vix_level=12.0)
    report_agreeing = ChiefMacroOfficer(manager_agree).analyze("US Macro Outlook")

    assert report_conflicting.confidence < report_agreeing.confidence
    # The macro bias direction itself must NOT flip because of the regime —
    # per the spec's explicit Trade Filter Rule, this is confirmation-only.
    assert report_conflicting.bias == report_agreeing.bias
    assert report_conflicting.bias_score == report_agreeing.bias_score


def test_extreme_vix_adds_warning_and_escalates_risk():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager, vix_level=40.0)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    assert any("Extreme volatility regime" in r for r in report.risks)
    assert report.risk_level == RiskLevel.HIGH


def test_market_regime_field_populated_with_component_scores():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager, vix_level=12.0)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    regime = report.market_regime
    assert regime.fed_policy_score is not None
    assert regime.real_yield_score is not None
    assert regime.treasury_yield_score is not None
    assert regime.vix_score is not None
    assert regime.market_impact  # populated dict
    assert regime.reasoning  # non-empty string


def test_market_regime_serializes_via_to_dict():
    manager = DataIntegrityManager(min_quality_threshold=50)
    _register_all_factors(manager, direction="bullish")
    _register_regime_sources(manager)
    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    d = report.to_dict()
    assert d["market_regime"] is not None
    assert "combined_score" in d["market_regime"]
    assert "display_band" in d["market_regime"]


def test_recalibrated_normalization_stops_moderate_moves_from_clamping():
    """
    Regression test for a real issue found in live testing: with the
    original uniform 5.0 normalization_pct on every factor, a live run
    showed 7 of 16 factors simultaneously clamped at +/-100 — several of
    them (Initial Jobless Claims, Housing Starts especially) are
    genuinely noisy series where a moderate, unremarkable move routinely
    exceeds a 5% threshold with no real economic significance. Proven
    directly: an 8% move — moderate for a noisy weekly/monthly series,
    but well past a tight 5% band — should NOT clamp for Initial Claims
    or Housing Starts (now 15.0) or PPI/JOLTS (now 10.0), but SHOULD
    still clamp for a tightly-banded factor like CPI (still 5.0), proving
    the recalibration is real and factor-specific, not a blanket loosening.
    """
    manager = DataIntegrityManager(min_quality_threshold=50)
    # An 8% move (oldest 100 -> newest 92, an 8% decline) for a
    # lower_is_bullish=True factor is bullish.
    eight_pct_move = [100, 96, 92]
    manager.register("FRED_INITIAL_CLAIMS", primary=FredLikeSource(eight_pct_move))
    manager.register("FRED_HOUSING_STARTS", primary=FredLikeSource(list(reversed(eight_pct_move))))  # False -> rising is bullish, so reverse
    manager.register("FRED_PPI", primary=FredLikeSource(eight_pct_move))
    manager.register("FRED_JOLTS", primary=FredLikeSource(list(reversed(eight_pct_move))))
    manager.register("FRED_CPI", primary=FredLikeSource(eight_pct_move))  # still 5.0 -> should still clamp

    report = ChiefMacroOfficer(manager).analyze("US Macro Outlook")
    factors_by_name = {f.name: f for f in report.factor_breakdown}

    assert abs(factors_by_name["Initial Jobless Claims"].score) < 100.0
    assert abs(factors_by_name["Housing Starts"].score) < 100.0
    assert abs(factors_by_name["PPI (Producer Prices)"].score) < 100.0
    assert abs(factors_by_name["JOLTS Job Openings"].score) < 100.0
    # CPI's threshold is unchanged (still 5.0) — an 8% move should still clamp it.
    assert abs(factors_by_name["CPI (Headline, YoY)"].score) == 100.0


# ---------------------------------------------------------------------- #
# Fed Funds Rate source — DFEDTARU (daily target range), not FEDFUNDS
# (monthly effective-rate average). See this module's 2026-09-17 update:
# a same-day FOMC hike couldn't show up via FEDFUNDS no matter how often
# the scheduled cycle ran, since FRED doesn't publish a month's FEDFUNDS
# average until the following month.
# ---------------------------------------------------------------------- #

def test_fed_funds_key_uses_daily_target_range_series_not_monthly_average():
    assert _FRED_SERIES_IDS[KEY_FED_FUNDS] == "DFEDTARU"


def test_register_macro_data_sources_widens_fetch_window_for_fed_funds_only():
    """
    DFEDTARU is a daily series (repeats between FOMC meetings) — the
    default 5-observation fetch window that's right for every other
    (monthly/quarterly) factor here would almost always see 5 identical
    days and read as flat. Confirm the Fed Funds registration specifically
    asks for a much wider window (90, matching agents.backtest_signals.
    fed_policy_signal's own lookback), while an ordinary monthly series
    still gets the plain default.
    """
    manager = DataIntegrityManager(min_quality_threshold=50)
    with patch("connectors.fred_connector.FredConnector.__init__", return_value=None) as mock_init:
        register_macro_data_sources(manager, fred_api_key="TEST_KEY")

    calls_by_series = {c.kwargs["series_id"]: c.kwargs for c in mock_init.call_args_list}
    assert calls_by_series["DFEDTARU"]["limit"] == 90
    assert calls_by_series["CPIAUCSL"]["limit"] == 5
