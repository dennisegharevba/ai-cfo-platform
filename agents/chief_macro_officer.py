"""
Chief Macro Officer — Institutional Fundamental Scoring Engine edition.

Per the upgrade spec: the platform no longer produces a market bias
primarily from COT — every major macroeconomic factor is evaluated
INDEPENDENTLY (its own current/previous/score/bias/importance weight/
confidence/timestamp/source) before contributing to one category-level
"Macroeconomic" score, via the shared engine in
agents/fundamental_scoring_engine.py.

This is Phase 1 of that engine (per an explicit scoping decision — see
docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md): Macro factor expansion +
the core scoring engine itself. Commodity Fundamentals, Sentiment, Risk,
and Seasonality categories follow in later phases using this exact same
pattern (score_category() + a list of FundamentalFactor).

15 real, free, FRED-backed factors (all via connectors.fred_connector.FredConnector,
no new connector needed):

    CPI, Core CPI, PPI, Core PCE          — inflation
    GDP, Retail Sales                      — growth
    Unemployment Rate, Nonfarm Payrolls,
        Average Hourly Earnings, JOLTS
        Job Openings, Initial Jobless
        Claims                             — labor market
    Trade-Weighted Dollar Index            — USD strength (a free FRED
                                              proxy for DXY, not the exact
                                              ICE-traded index)
    ICE BofA US Corporate Credit Spreads   — credit conditions
    U. Michigan Consumer Sentiment         — consumer confidence
    Housing Starts                         — housing
    Federal Debt (Total Public Debt)       — fiscal/structural (low weight,
                                              slow-moving, included for
                                              completeness per the spec's
                                              "Government Debt" line item)

HONEST SCOPE NOTE — deliberately NOT included, no free structured live
source available: PMIs (ISM's data is paid; FRED has no free substitute
for the exact ISM Manufacturing/Services indices), explicit Fed/ECB/BoE
policy-statement analysis (would need NLP over central bank text, not
structured numeric data), QT/QE tracking as a distinct line (partially
implied by the debt/credit-spread factors above, not modeled separately),
explicit geopolitical risk (no structured free feed), and Interest
Rates/Treasury Yields/Yield Curve as their own Macro line items — those
stay owned by agents.chief_bond_strategist.ChiefBondStrategist (this
platform's existing department for yield data), rather than being
duplicated here.

`forecast_value` is None for every factor — FRED reports actual published
values, not economist consensus estimates, and this platform has no free
source for those. Never fabricated; see models/fundamental_factor.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel
from models.fundamental_factor import FundamentalFactor, factor_bias_from_score

from .base_agent import BaseAgent
from .fundamental_scoring_engine import score_category
from .institutional_market_regime import (
    score_fed_policy, score_real_yield, score_treasury_yield, score_vix,
    combine_regime_scores, build_market_impact, build_regime_reasoning,
)
from .institutional_relationship import classify_alignment, apply_confidence_adjustment
from .risk_severity import worse_risk_level
from .trend_scoring import series_trend_score
from .trend_scoring import series_trend_score as _series_trend_score  # noqa: F401 — backward-compat re-export; agents/chief_bond_strategist.py imports this name directly

CATEGORY = "Macroeconomic"

# Registration keys this agent expects to find in the DataIntegrityManager.
# Kept as the original names (KEY_CPI, KEY_UNRATE) for backward
# compatibility with anything already importing them.
KEY_CPI = "FRED_CPI"
KEY_UNRATE = "FRED_UNRATE"
KEY_CORE_CPI = "FRED_CORE_CPI"
KEY_PPI = "FRED_PPI"
KEY_CORE_PCE = "FRED_CORE_PCE"
KEY_GDP = "FRED_GDP"
KEY_RETAIL_SALES = "FRED_RETAIL_SALES"
KEY_NFP = "FRED_NFP"
KEY_AVG_HOURLY_EARNINGS = "FRED_AVG_HOURLY_EARNINGS"
KEY_JOLTS = "FRED_JOLTS"
KEY_INITIAL_CLAIMS = "FRED_INITIAL_CLAIMS"
KEY_DOLLAR_INDEX = "FRED_DOLLAR_INDEX"
KEY_CREDIT_SPREADS = "FRED_CREDIT_SPREADS"
KEY_CONSUMER_CONFIDENCE = "FRED_CONSUMER_CONFIDENCE"
KEY_HOUSING_STARTS = "FRED_HOUSING_STARTS"
KEY_FEDERAL_DEBT = "FRED_FEDERAL_DEBT"

# --- Institutional Market Regime Filter keys ---
# Per an explicit later upgrade (see docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md):
# Federal Reserve Policy, 10Y TIPS Real Yield, 10Y Treasury Yield, and VIX
# act as a confidence-adjusting confirmation layer alongside the 16 Macro
# factors above — NOT folded into the Macro category score itself (they're
# peer-level regime components, matching the spec's own OUTPUT FORMAT,
# which shows "Macro Report" and "Federal Reserve"/"Real Yields"/"US10Y
# Treasury Yield"/"VIX" as separate lines, not sub-items of Macro).
KEY_FED_FUNDS = "FRED_FED_FUNDS"
KEY_REAL_YIELD = "FRED_REAL_YIELD"
KEY_VIX = "FRED_VIX"
# Reuses agents.chief_bond_strategist.KEY_DGS10's exact string so the
# DataIntegrityManager serves both departments from the SAME cached
# dataset — one fetch, not two — rather than importing that module
# directly (which would create a cross-department import dependency for
# no benefit; the string value itself is the only thing that needs to match).
KEY_DGS10_FOR_REGIME = "FRED_DGS10"

# Baseline confidence for a single-series factor with a computable trend.
# Simpler than the multi-component confidence models elsewhere in this
# codebase (e.g. positioning agents' momentum/extreme adjustments) because
# each Macro factor here is one signal, not several blended together.
FACTOR_BASE_CONFIDENCE = 75.0

# (display name, dataset key, lower_is_bullish, importance_weight 1-10, normalization_pct)
# lower_is_bullish=True means a FALLING value is the bullish direction for
# the general growth/risk regime this agent models (e.g. falling
# inflation, falling unemployment); False means a RISING value is bullish
# (e.g. rising GDP, rising payrolls).
#
# normalization_pct calibration — UPDATED per a live run that showed 7 of
# 16 factors clamped at the +/-100 extreme simultaneously. Root cause:
# FredConnector fetches a fixed 5 observations for every series (see
# connectors/fred_connector.py), but 5 observations spans a WILDLY
# different real time window depending on each series' native reporting
# frequency — 5 WEEKS for a weekly series (Initial Jobless Claims), 5
# MONTHS for most monthly series, ~15 MONTHS for a quarterly series (GDP,
# Federal Debt). Applying the SAME uniform 5.0 threshold to all of them
# meant naturally noisy/fast-moving series were almost guaranteed to hit
# the clamp regardless of whether current conditions were actually
# unusual, while naturally-compounding LEVEL series (GDP, Federal Debt
# both trend upward over any 15-month window under nearly any
# conditions) were structurally biased toward one direction.
#
# These are REASONED, DEFENSIBLE first-pass recalibrations based on each
# series' well-documented real-world volatility characteristics — NOT
# values back-tested against this series' own actual historical
# distribution (this platform has no live network access to compute
# that from this environment). agents/backtest_engine.py's correlation
# validation could be extended to properly calibrate these empirically
# once real historical data is available — a natural, concrete follow-up.
_FACTOR_SPECS = [
    ("CPI (Headline, YoY)", KEY_CPI, True, 8.0, 5.0),
    ("Core CPI (YoY)", KEY_CORE_CPI, True, 8.0, 5.0),
    # PPI is more volatile than CPI (production-side prices swing harder
    # than consumer prices) — widened from 5.0 after a live run clamped it.
    ("PPI (Producer Prices)", KEY_PPI, True, 5.0, 10.0),
    ("Core PCE (Fed's preferred inflation gauge)", KEY_CORE_PCE, True, 9.0, 5.0),
    # GDP is a LEVEL series that compounds upward over any multi-quarter
    # window under nearly any conditions (nominal GDP growth of ~4-6%/yr
    # is ordinary, not a bullish signal on its own) — widened from 5.0 so
    # only genuinely ABOVE-TREND growth scores near the maximum.
    ("GDP", KEY_GDP, False, 7.0, 10.0),
    ("Retail Sales", KEY_RETAIL_SALES, False, 6.0, 5.0),
    ("Unemployment Rate", KEY_UNRATE, True, 8.0, 5.0),
    ("Nonfarm Payrolls", KEY_NFP, False, 8.0, 5.0),
    ("Average Hourly Earnings", KEY_AVG_HOURLY_EARNINGS, False, 4.0, 5.0),
    # JOLTS Job Openings is a genuinely volatile monthly series — widened
    # from 5.0 after a live run clamped it.
    ("JOLTS Job Openings", KEY_JOLTS, False, 5.0, 10.0),
    # Initial Jobless Claims is WEEKLY and famously noisy week-to-week
    # (holidays, weather, and pure reporting noise routinely move it
    # 5-10%+ with no underlying economic-trend change) — widened
    # significantly from 5.0, the most aggressive change here, since this
    # is the single noisiest series in the whole factor list.
    ("Initial Jobless Claims", KEY_INITIAL_CLAIMS, True, 6.0, 15.0),
    ("Trade-Weighted Dollar Index", KEY_DOLLAR_INDEX, True, 5.0, 5.0),
    ("Credit Spreads (ICE BofA US Corporate OAS)", KEY_CREDIT_SPREADS, True, 7.0, 5.0),
    # Consumer Confidence (U. Michigan) can move sharply during genuine
    # sentiment shifts. UPDATE: a first live run clamped it at 5.0; widened
    # to 10.0 — but a SECOND live run showed it STILL clamping at exactly
    # -100.0 even at 10.0, with the underlying reading (49.5) genuinely in
    # rare, historically depressed territory. Widened further to 15.0
    # (matching Initial Claims/Housing Starts, this factor list's most
    # aggressively-widened cases) based on this new evidence. Honest
    # unknown: it's not yet clear whether this fully resolves the
    # clamping or whether the underlying move is simply large enough that
    # some proximity to the extreme is an accurate signal, not a
    # miscalibration — worth checking with a third live run rather than
    # assuming this is the final word.
    ("Consumer Confidence (U. Michigan)", KEY_CONSUMER_CONFIDENCE, False, 5.0, 15.0),
    # Housing Starts is widely regarded as the single noisiest major US
    # economic indicator (weather, permitting-timing, and seasonal
    # adjustment quirks routinely swing it 10-20%+ with no real trend
    # change) — widened significantly from 5.0, alongside Initial Claims.
    ("Housing Starts", KEY_HOUSING_STARTS, False, 4.0, 15.0),
    # Federal Debt is a LEVEL series that grows steadily under nearly any
    # political/fiscal regime — widened from 5.0 so this factor reflects
    # genuinely ACCELERATING debt growth, not just "debt went up again,"
    # which it does almost every quarter.
    ("Federal Debt (Total Public Debt)", KEY_FEDERAL_DEBT, True, 3.0, 8.0),
]


def _value_n_days_ago(history: List[dict], days: int) -> Optional[float]:
    """
    Find the value closest to (but not after) `days` before the most
    recent reading in a newest-first FRED-style history list. Returns
    None if the history doesn't reach back far enough — never
    extrapolates or guesses a value that isn't actually in the data.
    """
    if not history:
        return None
    try:
        latest_date = datetime.strptime(history[0]["date"], "%Y-%m-%d")
    except (KeyError, ValueError, TypeError):
        return None

    target_date = latest_date - timedelta(days=days)
    for row in history:
        try:
            row_date = datetime.strptime(row["date"], "%Y-%m-%d")
            row_value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        if row_date <= target_date:
            return row_value
    return None


def _build_factor(
    name: str, dataset: Optional[Dataset], lower_is_bullish: bool, importance_weight: float, normalization_pct: float,
) -> Optional[FundamentalFactor]:
    """Build one FundamentalFactor from an already-fetched, already-validated
    FRED Dataset. Returns None if the dataset is missing or its trend can't
    be computed — callers must handle that as a data gap, never fabricate."""
    if dataset is None:
        return None

    history = dataset.payload.get("history", [])
    score = series_trend_score(history, lower_is_bullish=lower_is_bullish, normalization_pct=normalization_pct)
    if score is None:
        return None

    current_value: Optional[float] = None
    try:
        current_value = float(dataset.payload.get("latest_value"))
    except (TypeError, ValueError):
        pass

    previous_value: Optional[float] = None
    if len(history) >= 2:
        try:
            previous_value = float(history[1].get("value"))
        except (TypeError, ValueError):
            pass

    last_updated = dataset.provider_timestamp or dataset.time_collected

    return FundamentalFactor(
        name=name,
        category=CATEGORY,
        current_value=current_value,
        previous_value=previous_value,
        forecast_value=None,  # no free consensus-forecast source — see module docstring
        score=round(score, 1),
        bias=factor_bias_from_score(score),
        importance_weight=importance_weight,
        confidence=FACTOR_BASE_CONFIDENCE,
        source=dataset.source,
        last_updated=last_updated,
    )


# Real FRED series IDs for each registration key above — used only by
# register_macro_data_sources() below, kept separate from _FACTOR_SPECS so
# the scoring loop doesn't need to carry a field it never uses.
_FRED_SERIES_IDS = {
    KEY_CPI: "CPIAUCSL",
    KEY_CORE_CPI: "CPILFESL",
    KEY_PPI: "PPIACO",
    KEY_CORE_PCE: "PCEPILFE",
    KEY_GDP: "GDP",
    KEY_RETAIL_SALES: "RSAFS",
    KEY_UNRATE: "UNRATE",
    KEY_NFP: "PAYEMS",
    KEY_AVG_HOURLY_EARNINGS: "CES0500000003",
    KEY_JOLTS: "JTSJOL",
    KEY_INITIAL_CLAIMS: "ICSA",
    KEY_DOLLAR_INDEX: "DTWEXBGS",
    KEY_CREDIT_SPREADS: "BAMLC0A0CM",
    KEY_CONSUMER_CONFIDENCE: "UMCSENT",
    KEY_HOUSING_STARTS: "HOUST",
    KEY_FEDERAL_DEBT: "GFDEBTN",
    # DFEDTARU — Federal Funds Target Range, UPPER LIMIT — not FEDFUNDS.
    # Update, 2026-09-17: this was FEDFUNDS (the MONTHLY average of the
    # effective federal funds rate) until a same-day 25bp hike (2026-09-16)
    # exposed a real, honest gap — FEDFUNDS doesn't publish a given month's
    # number until early the following month, and even then it's a blended
    # average across pre- and post-hike days, so an FOMC decision could
    # never show up here for weeks no matter how often this cycle ran.
    # DFEDTARU is published DAILY and reflects a new target range "as of
    # that day" per FRED's own series metadata — the same FOMC decision
    # this platform now picks up on the very next scheduled cycle after
    # FRED posts it, typically the next business day. See
    # docs/ARCHITECTURE_SWING_SIGNAL.md's 2026-09-17 update and
    # agents/institutional_market_regime.py's module docstring for the
    # full account, including the one honest tradeoff this choice accepts
    # (upper limit only, not the target range midpoint — see there).
    KEY_FED_FUNDS: "DFEDTARU",
    KEY_REAL_YIELD: "DFII10",
    KEY_VIX: "VIXCLS",
    KEY_DGS10_FOR_REGIME: "DGS10",
}

# Per-series overrides to FredConnector's default 5-observation fetch
# window. Every OTHER series above is monthly/quarterly, where 5
# observations is a sensible several-month/quarter trend window. DFEDTARU
# is DAILY (it repeats the same value every day between FOMC meetings), so
# 5 observations would only be the last 5 calendar days — almost always
# flat, and too narrow a window to give score_fed_policy() a real trend to
# read. 90 matches the same lookback agents.backtest_signals.fed_policy_signal()
# already uses for its own two-point historical comparison, so live and
# backtested Fed Policy scoring stay on the same real-world time window.
_FRED_SERIES_LIMIT_OVERRIDES = {
    KEY_FED_FUNDS: 90,
}


def register_macro_data_sources(manager, fred_api_key: str) -> None:
    """
    Register every FRED series this agent needs, skipping any key already
    registered (so calling this alongside other registrations, or calling
    it more than once across dashboard reruns, is always safe). Shared by
    every caller (demo scripts, scripts/run_daily_cycle.py, the dashboard)
    so the 16-series registration list lives in exactly one place rather
    than being copy-pasted three times.
    """
    from connectors.fred_connector import FredConnector  # local import: avoids a hard dependency for callers that only need the class/keys

    for key, series_id in _FRED_SERIES_IDS.items():
        if not manager.is_registered(key):
            limit = _FRED_SERIES_LIMIT_OVERRIDES.get(key, 5)
            manager.register(key, primary=FredConnector(series_id=series_id, api_key=fred_api_key, limit=limit))


class ChiefMacroOfficer(BaseAgent):
    department = "Chief Macro Officer"

    def required_dataset_keys(self) -> List[str]:
        macro_keys = [key for (_, key, _, _, _) in _FACTOR_SPECS]
        regime_keys = [KEY_FED_FUNDS, KEY_REAL_YIELD, KEY_VIX, KEY_DGS10_FOR_REGIME]
        # dict.fromkeys de-dupes while preserving order, in case a regime
        # key ever coincides with an existing Macro factor key.
        return list(dict.fromkeys(macro_keys + regime_keys))

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        factors: List[FundamentalFactor] = []
        data_gaps: List[str] = []

        for name, key, lower_is_bullish, weight, norm_pct in _FACTOR_SPECS:
            factor = _build_factor(name, usable.get(key), lower_is_bullish, weight, norm_pct)
            if factor is not None:
                factors.append(factor)
            elif key not in usable:
                # Already recorded as a data_gap by BaseAgent.analyze() for
                # missing/blocked datasets — nothing to add here.
                pass
            else:
                # Dataset was usable but its trend couldn't be computed
                # (e.g. insufficient history) — a gap specific to this factor.
                data_gaps.append(f"{key} (insufficient history to score)")

        category_result = score_category(CATEGORY, factors)
        risk_level = category_result.risk_level

        evidence = [
            f"{f.name}: {f.bias.value} (score {f.score:+.1f}, current={f.current_value}, "
            f"as of {f.last_updated.date()})"
            for f in factors
        ]
        catalysts = [f"{f.name} is supportive (score {f.score:+.1f})" for f in factors if f.bias.value == "bullish"]
        risks = [f"{f.name} is a headwind (score {f.score:+.1f})" for f in factors if f.bias.value == "bearish"]

        if len(factors) < len(_FACTOR_SPECS) // 2:
            # Fewer than half the expected factors came through usable —
            # this reading is thin, regardless of what score_category computed.
            risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)
            risks.append(
                f"Only {len(factors)} of {len(_FACTOR_SPECS)} Macro factors were usable this cycle — "
                f"treat this reading as incomplete"
            )

        # --- Institutional Market Regime Filters ---
        # A confidence-adjusting confirmation layer, NOT folded into the
        # Macro category score itself — see
        # docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md. Every component
        # is computed only from data that actually came through; a missing
        # component contributes nothing (see agents.institutional_market_regime's
        # own renormalization), never a fabricated reading.
        fed_funds_ds = usable.get(KEY_FED_FUNDS)
        fed_policy_score = None
        if fed_funds_ds is not None:
            fed_trend = series_trend_score(fed_funds_ds.payload.get("history", []), lower_is_bullish=True)
            fed_policy_score = score_fed_policy(fed_trend)

        real_yield_ds = usable.get(KEY_REAL_YIELD)
        real_yield_score = None
        if real_yield_ds is not None:
            history = real_yield_ds.payload.get("history", [])
            current = None
            try:
                current = float(real_yield_ds.payload.get("latest_value"))
            except (TypeError, ValueError):
                pass
            month_ago = _value_n_days_ago(history, 30)
            if current is not None and month_ago is not None:
                real_yield_score = score_real_yield((current - month_ago) * 100)  # percent -> bps

        treasury_ds = usable.get(KEY_DGS10_FOR_REGIME)
        treasury_yield_score = None
        if treasury_ds is not None:
            history = treasury_ds.payload.get("history", [])
            current = None
            try:
                current = float(treasury_ds.payload.get("latest_value"))
            except (TypeError, ValueError):
                pass
            week_ago = _value_n_days_ago(history, 7)
            if current is not None and week_ago is not None:
                treasury_yield_score = score_treasury_yield((current - week_ago) * 100)  # percent -> bps

        vix_ds = usable.get(KEY_VIX)
        vix_level = None
        if vix_ds is not None:
            try:
                vix_level = float(vix_ds.payload.get("latest_value"))
            except (TypeError, ValueError):
                pass
        vix_score = score_vix(vix_level)

        regime = combine_regime_scores(
            macro_score=category_result.category_score if factors else None,
            fed_policy_score=fed_policy_score,
            real_yield_score=real_yield_score,
            treasury_yield_score=treasury_yield_score,
            vix_score=vix_score,
            vix_level=vix_level,
        )
        regime.market_impact = build_market_impact(fed_policy_score, real_yield_score, treasury_yield_score)
        regime.reasoning = build_regime_reasoning(regime)

        if regime.vix_warning_message:
            risk_level = worse_risk_level(risk_level, RiskLevel.HIGH)
            risks.append(regime.vix_warning_message)

        # Per the spec's explicit "Trade Filter Rule": the regime score
        # CONFIRMS or WARNS — it must never override the Macro category's
        # own directional bias. Reusing the exact same alignment
        # classification + confidence adjustment already built for the
        # (now-orphaned) commercial/speculative COT relationship — see
        # docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md for why this
        # reuse was a deliberate choice, not an accident.
        final_confidence = category_result.category_confidence
        alignment_status = None
        if factors:
            alignment_status = classify_alignment(category_result.category_score, regime.combined_score)
            final_confidence = apply_confidence_adjustment(category_result.category_confidence, alignment_status)

        evidence.append(
            f"Institutional Market Regime: {regime.display_band()} ({regime.display_score():.0f}/100) — {regime.reasoning}"
        )
        for asset, label in regime.market_impact.items():
            evidence.append(f"Market impact — {asset}: {label}")

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=category_result.bias,
            bias_score=category_result.category_score,
            confidence=round(final_confidence, 1),
            risk_level=risk_level,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=data_gaps,  # merged with BaseAgent's own missing-dataset gaps automatically
            factor_breakdown=factors,
            market_regime=regime,
        )
