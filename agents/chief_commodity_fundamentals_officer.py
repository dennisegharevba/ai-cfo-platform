"""
Chief Commodity Fundamentals Officer.

Per the Institutional Fundamental Scoring Engine upgrade spec: "Commodity
Fundamentals" (supply/demand/inventories/etc.) is its own category,
distinct from COT positioning — COT stays a small, supporting-only signal
(agents.chief_commodity_analyst.ChiefCommodityAnalyst, already weighted at
0.4 vs. fundamentals' 1.0 default in ChiefStrategyOfficer — see
docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md). This agent is the
fundamentals side: real supply/demand data, independently scored, feeding
into the exact same score_category() engine Chief Macro Officer uses.

HONEST SCOPE — per the same "skip factors with no free live source" rule
already applied to Macro: of the full spec's Commodity Fundamentals
wishlist (Supply, Demand, Inventories, Mine Production, Central Bank
Buying, ETF Flows, Jewellery Demand, Industrial Demand, OPEC, Weather,
Shipping, Export Data, Import Data, Seasonality, Storage Levels, Cost of
Production), only INVENTORY/STORAGE data (energy) has a genuine free,
structured, live source: the U.S. Energy Information Administration's free
public API (connectors/eia_connector.py).

PRECIOUS METALS (Gold, Silver, Platinum, Palladium) — per an explicit
later decision — are now fundamentally backed too, using the SAME
US-Dollar-related fundamentals Chief Macro Officer already tracks (real
yields, the Dollar Index, Fed Funds Rate), on the reasoning that Gold
(and other precious metals) are priced in US Dollars, so USD strength/
weakness is a genuine, direct fundamental driver — not COT positioning
alone. These factors REUSE the exact same DataIntegrityManager keys Chief
Macro Officer registers (agents.chief_macro_officer.KEY_REAL_YIELD,
KEY_DOLLAR_INDEX, KEY_FED_FUNDS) rather than fetching the same FRED series
a second time under a commodity-namespaced key — one fetch serves both
departments. See `register_commodity_fundamentals_sources()`'s docstring
for what this means for registration order.

Mine production, central bank gold buying, ETF flows, and jewellery/
industrial demand remain NOT modeled — no free structured live source for
any of them — exactly like PMIs were handled for Chief Macro Officer:
absent, not stubbed, not faked.

Every other commodity (Copper, and every agricultural commodity) still has
an empty factor list for this department, which correctly produces a
neutral/zero-confidence/HIGH-risk result via score_category() — an honest
"no fundamentals data available for this commodity yet."

This agent is instantiated per-commodity (same pattern as
agents.positioning_agent_base.PositioningAgent), since which factors are
even relevant is commodity-specific.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel
from models.fundamental_factor import FundamentalFactor, factor_bias_from_score

from .base_agent import BaseAgent
from .factor_narrative import describe_factor
from .fundamental_scoring_engine import score_category
from .risk_severity import worse_risk_level
from .trend_scoring import series_trend_score
from .chief_macro_officer import KEY_REAL_YIELD, KEY_DOLLAR_INDEX, KEY_FED_FUNDS

CATEGORY = "Commodity Fundamentals"
FACTOR_BASE_CONFIDENCE = 70.0  # slightly below Macro's 75 — EIA weekly data is one release, same single-signal reasoning as Macro factors

# (display name, key suffix, lower_is_bullish, importance_weight 1-10,
#  normalization_pct, override_key)
# Keyed by commodity display name (must match what Chief Commodity Analyst
# uses for asset_or_theme, e.g. "Gold", "Crude Oil", so a Strategy Officer
# synthesis for the same asset picks up both departments' reports).
#
# override_key: when set (precious metals below), this is the EXACT
# DataIntegrityManager key to read from directly — reusing a dataset Chief
# Macro Officer already registers (e.g. KEY_REAL_YIELD) — rather than
# building a commodity-namespaced key via _dataset_key(). This is what
# lets Gold/Silver/Platinum/Palladium share the SAME fetched Real Yield/
# Dollar Index/Fed Funds Rate dataset Chief Macro Officer already uses,
# instead of fetching the identical FRED series a second time. When None
# (the EIA-based energy factors), the commodity-namespaced key from
# _dataset_key() is used, as before.
#
# lower_is_bullish=True means FALLING inventories is the bullish direction
# (tighter supply -> supportive of price) for the energy factors; for the
# precious-metals USD factors, lower_is_bullish=True means a FALLING
# Real Yield / Dollar Index / Fed Funds Rate is bullish for Gold — lower
# real yields reduce the opportunity cost of holding a non-yielding asset,
# and a weaker dollar makes dollar-priced gold cheaper in other currencies,
# both standard, widely-cited drivers.
#
# normalization_pct for the EIA inventory factors — UPDATED after a live
# run (with a real, working EIA_API_KEY) showed Crude Oil Inventories
# clamped at the exact +100.0 extreme, the same signature that led to the
# Macro factor recalibration documented in
# docs/ARCHITECTURE_NORMALIZATION_RECALIBRATION.md. The live agent fetches
# a 12-observation window (~12 weeks of EIA weekly data — see
# EiaConnector's periods_history default), over which BOTH crude oil and
# especially natural gas inventories are known to swing significantly due
# to well-documented SEASONAL patterns (summer driving-season draws,
# winter heating-season withdrawals) — a 5%+ move over a 3-month window
# is often routine seasonal behavior, not an extreme current condition.
# Natural Gas Storage is widened further than Crude Oil since its
# seasonal injection/withdrawal cycle is substantially more pronounced.
# Same honest caveat as the Macro recalibration: these are reasoned,
# defensible first-pass values based on known energy-market seasonal
# characteristics, not back-tested against this series' own historical
# distribution (no live network access from this environment to compute
# that) — a natural candidate for agents/backtest_engine.py once real
# historical EIA data is available.
COMMODITY_FACTOR_SPECS: Dict[str, List[tuple]] = {
    "Crude Oil": [
        ("Crude Oil Inventories (EIA Weekly Stocks)", "crude_oil_inventories", True, 7.0, 10.0, None),
    ],
    "Natural Gas": [
        ("Natural Gas Storage (EIA Weekly)", "natural_gas_storage", True, 7.0, 20.0, None),
    ],
    "Gold": [
        ("US 10Y Real Yield (TIPS)", "real_yield", True, 8.0, 5.0, KEY_REAL_YIELD),
        ("Trade-Weighted Dollar Index", "dollar_index", True, 7.0, 5.0, KEY_DOLLAR_INDEX),
        ("Federal Funds Rate", "fed_funds", True, 6.0, 5.0, KEY_FED_FUNDS),
    ],
    # Every other commodity intentionally has no entry here — see module
    # docstring. required_dataset_keys() below returns [] for them, and
    # score_category() correctly reports neutral/zero-confidence/HIGH risk
    # for an empty factor list, same as any other missing-data case.
}

# Silver, Platinum, and Palladium are all dollar-priced precious metals
# with the same USD-fundamentals sensitivity as Gold (real yields, dollar
# strength, Fed policy) — sharing Gold's exact factor list rather than
# duplicating it. Each ALSO has real industrial-demand drivers this
# platform doesn't model (no free source) — the USD factors below are a
# genuine, partial fundamental backing, not a claim to fully capture
# what drives these metals.
for _metal in ("Silver", "Platinum", "Palladium"):
    COMMODITY_FACTOR_SPECS[_metal] = COMMODITY_FACTOR_SPECS["Gold"]

# config/cftc_markets.py (this platform's CFTC positioning data) uses "WTI
# Crude Oil" as its display name, while this module's own tests/demo/
# dashboard code use the shorter "Crude Oil" — rather than picking one and
# breaking the other's callers, both point at the identical factor list so
# config/watchlist.py's lookup (which uses the CFTC naming convention)
# finds the same real, configured factors "Crude Oil" already has.
COMMODITY_FACTOR_SPECS["WTI Crude Oil"] = COMMODITY_FACTOR_SPECS["Crude Oil"]

# EIA route/facets for each (commodity, key_suffix) pair above — the single
# canonical source every caller (demo scripts, the dashboard, the scheduled
# daily cycle) should register from, rather than each hardcoding its own
# copy of these route strings (which would risk drift between callers).
# See connectors/eia_connector.py's docstring for the "not verified live"
# caveat on these exact route/facet values.
EIA_ROUTE_SPECS: Dict[tuple, tuple] = {
    ("Crude Oil", "crude_oil_inventories"): (
        "petroleum/stoc/wstk", {"product": ["EPC0"], "duoarea": ["NUS"]},
    ),
    ("Natural Gas", "natural_gas_storage"): (
        "natural-gas/stor/wkly", {"duoarea": ["NUS"]},
    ),
}
EIA_ROUTE_SPECS[("WTI Crude Oil", "crude_oil_inventories")] = EIA_ROUTE_SPECS[("Crude Oil", "crude_oil_inventories")]

# Update, 2026-09-17: real narrative content — see agents/factor_narrative.py's
# module docstring (this is the exact department the user's Gold screenshot
# complaint was about: "not showing any real fundamental reasons... still
# stick to COT reports"). Unlike Chief Macro Officer's narrative meta
# (deliberately asset-agnostic, since that report is shared across every
# asset), these factors genuinely ARE asset-specific — the whole point of
# this department is "why USD strength/rates matter for precious metals
# specifically" and "why inventories matter for this specific commodity" —
# so the meaning text names the metal/commodity directly. Keyed by exact
# display name from COMMODITY_FACTOR_SPECS.
_FACTOR_NARRATIVE_META = {
    "US 10Y Real Yield (TIPS)": (
        "%",
        "falling real yields reduce the opportunity cost of holding non-yielding gold",
        "rising real yields increase the opportunity cost of holding non-yielding gold",
    ),
    "Trade-Weighted Dollar Index": (
        "index",
        "a weaker dollar makes dollar-priced gold cheaper for holders of other currencies",
        "a stronger dollar makes dollar-priced gold more expensive for holders of other currencies",
    ),
    "Federal Funds Rate": (
        "%",
        "a falling policy rate reduces the opportunity cost of holding non-yielding gold",
        "a rising or elevated policy rate increases the opportunity cost of holding non-yielding gold",
    ),
    "Crude Oil Inventories (EIA Weekly Stocks)": (
        "K",
        "falling inventories point to tightening supply, typically supportive for crude prices",
        "rising inventories point to loosening supply, typically a headwind for crude prices",
    ),
    "Natural Gas Storage (EIA Weekly)": (
        "Bcf",
        "falling storage levels point to tightening supply, typically supportive for natural gas prices",
        "rising storage levels point to loosening supply, typically a headwind for natural gas prices",
    ),
}


def _resolve_key(commodity: str, suffix: str, override_key: Optional[str]) -> str:
    """The actual DataIntegrityManager key for one factor: the shared
    override_key if set (precious metals' USD factors), otherwise the
    commodity-namespaced EIA key (energy factors)."""
    return override_key if override_key is not None else _dataset_key(commodity, suffix)


def register_commodity_fundamentals_sources(manager, commodity: str, eia_api_key: str) -> None:
    """
    Register every EIA connector `commodity` needs, skipping any key
    already registered. A no-op for commodities with no configured
    factors, or whose factors are ALL shared/override keys (e.g. Gold's
    Real Yield/Dollar Index/Fed Funds Rate) — those are registered by
    agents.chief_macro_officer.register_macro_data_sources() instead, not
    here. A caller running Chief Commodity Fundamentals Officer for Gold/
    Silver/Platinum/Palladium should call BOTH registration functions —
    every existing caller in this codebase (demo script, dashboard,
    scripts/run_daily_cycle.py) already registers Macro's sources
    separately, so this is naturally satisfied, not an extra step.
    """
    from connectors.eia_connector import EiaConnector  # local import: avoids a hard dependency for callers that only need the class/keys

    for name, suffix, _, _, _, override_key in COMMODITY_FACTOR_SPECS.get(commodity, []):
        if override_key is not None:
            continue  # registered by Chief Macro Officer's own registration function instead
        key = _dataset_key(commodity, suffix)
        if manager.is_registered(key):
            continue
        route_spec = EIA_ROUTE_SPECS.get((commodity, suffix))
        if route_spec is None:
            continue
        route, facets = route_spec
        manager.register(key, primary=EiaConnector(route=route, facets=facets, api_key=eia_api_key))


def _dataset_key(commodity: str, key_suffix: str) -> str:
    """Namespaced DataIntegrityManager key for one commodity's one factor."""
    safe_commodity = commodity.upper().replace(" ", "_")
    return f"EIA_{safe_commodity}_{key_suffix.upper()}"


def _build_factor(
    name: str, dataset: Optional[Dataset], lower_is_bullish: bool, importance_weight: float, normalization_pct: float,
) -> Optional[FundamentalFactor]:
    """Same construction logic as agents.chief_macro_officer._build_factor —
    kept as a local copy rather than a shared import since the two agents'
    factor-building steps are simple enough that sharing would add more
    indirection than it saves; revisit if a third category needs this
    exact shape (matching this codebase's own "extract on 2nd/3rd
    consumer, not before" convention)."""
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

    return FundamentalFactor(
        name=name,
        category=CATEGORY,
        current_value=current_value,
        previous_value=previous_value,
        forecast_value=None,  # EIA reports actuals, not consensus forecasts
        score=round(score, 1),
        bias=factor_bias_from_score(score),
        importance_weight=importance_weight,
        confidence=FACTOR_BASE_CONFIDENCE,
        source=dataset.source,
        last_updated=dataset.provider_timestamp or dataset.time_collected,
    )


class ChiefCommodityFundamentalsOfficer(BaseAgent):
    department = "Chief Commodity Fundamentals Officer"

    def __init__(self, manager, commodity: str, min_quality: float = 60.0):
        super().__init__(manager, min_quality)
        self.commodity = commodity
        self._factor_specs = COMMODITY_FACTOR_SPECS.get(commodity, [])

    def required_dataset_keys(self) -> List[str]:
        return [_resolve_key(self.commodity, suffix, override_key) for (_, suffix, _, _, _, override_key) in self._factor_specs]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        factors: List[FundamentalFactor] = []
        data_gaps: List[str] = []

        if not self._factor_specs:
            # No configured factors for this commodity at all — see module
            # docstring. Nothing to fetch, nothing to score; honest and
            # immediate rather than pretending to try.
            data_gaps.append(f"No free Commodity Fundamentals data source configured for '{self.commodity}' yet")

        for name, suffix, lower_is_bullish, weight, norm_pct, override_key in self._factor_specs:
            key = _resolve_key(self.commodity, suffix, override_key)
            factor = _build_factor(name, usable.get(key), lower_is_bullish, weight, norm_pct)
            if factor is not None:
                factors.append(factor)
            elif key not in usable:
                pass  # already recorded as a gap by BaseAgent.analyze()
            else:
                data_gaps.append(f"{key} (insufficient history to score)")

        category_result = score_category(CATEGORY, factors)
        risk_level = category_result.risk_level

        # Real narrative, not a score label — see agents/factor_narrative.py
        # and _FACTOR_NARRATIVE_META above for the 2026-09-17 fix (the
        # direct fix for the user's "not real fundamental interpretations,
        # I want real fundamental interpretations not just based on COT
        # reports" complaint on Gold's Trade Decision Engine page).
        evidence = [
            describe_factor(f, *_FACTOR_NARRATIVE_META.get(f.name, ("", "", "")))
            for f in factors
        ]
        catalysts = [
            describe_factor(f, *_FACTOR_NARRATIVE_META.get(f.name, ("", "", "")))
            for f in factors if f.bias.value == "bullish"
        ]
        risks = [
            describe_factor(f, *_FACTOR_NARRATIVE_META.get(f.name, ("", "", "")))
            for f in factors if f.bias.value == "bearish"
        ]

        if self._factor_specs and len(factors) < len(self._factor_specs):
            risk_level = worse_risk_level(risk_level, RiskLevel.ELEVATED)

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=category_result.bias,
            bias_score=category_result.category_score,
            confidence=category_result.category_confidence,
            risk_level=risk_level,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=data_gaps,
            factor_breakdown=factors,
        )
