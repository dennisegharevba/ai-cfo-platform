"""
Opportunity screener — scans many assets across multiple classes
(equities, commodities, FX, crypto) and ranks them by a fast, real,
volatility-normalized technical conviction score, to surface promising
candidates rather than requiring a fixed, manually-chosen asset list
every time.

HONEST NAMING — read this before using the word "probability" anywhere
near this module's output. "Conviction score" here means the STRENGTH
of a real, fast technical signal — RSI/MACD confirmation from
agents.trade_scoring.build_synthetic_technical_report(), combined with
agents.technical_indicators.volatility_normalized_trend_score() for the
actual trend-strength component (NOT that function's own flat-normalized
bias_score — see that function's docstring and
docs/ARCHITECTURE_OPPORTUNITY_SCREENER.md for why: a flat normalization
threshold structurally favors whichever asset class happens to be more
volatile when ranking across genuinely different classes together, found
via a real live run that came back essentially 100% volatile growth
stocks for exactly that reason). This is still NOT a rigorously
backtested win-probability — that would require running
agents.strategy_backtest.simulate_strategy() per asset, far too slow for
hundreds of assets in one screening pass (the same honest scope note
already applies to scripts/run_backtest_all.py — see
docs/ARCHITECTURE_BATCH_BACKTESTING.md). "Highest probability" in casual
usage and "highest conviction technical score" are DIFFERENT claims. A
signal ranked highly here is a good STRATEGY-BACKTESTING CANDIDATE, not
a validated winner — run scripts/run_strategy_backtest.py against any
promising candidate before trusting it with real sizing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .trade_scoring import build_synthetic_technical_report
from .technical_indicators import volatility_normalized_trend_score, volume_confirmation_ratio, volume_confirmation_multiplier
from .risk_calculations import annualized_volatility


@dataclass
class ScreenedOpportunity:
    label: str
    ticker: str
    asset_class: str
    bias_score: float
    confidence: float
    direction: str          # "long" or "short"
    conviction_score: float  # see module docstring for exactly what this does and doesn't mean
    annualized_vol_pct: float  # the asset's own volatility used to normalize bias_score — exposed so the real
                               # numbers driving a ranking can be inspected directly, not just trusted blindly


def _price_history_to_technical_input(price_history_oldest_first: List[Tuple[date, float]]) -> List[dict]:
    """
    Converts the (date, price) OLDEST-FIRST tuple shape used by
    scripts.run_backtest._fetch_price_history() into the NEWEST-FIRST
    dict shape agents.trade_scoring.build_synthetic_technical_report()
    expects (its own docstring: "newest-first price history"). Two
    different, real, already-established conventions elsewhere in this
    platform — bridged here rather than changing either one.
    """
    return [
        {"close": price, "date": d.isoformat() if hasattr(d, "isoformat") else str(d)}
        for d, price in reversed(price_history_oldest_first)
    ]


def screen_asset(
    label: str, ticker: str, asset_class: str, price_history_oldest_first: List[Tuple[date, float]],
    volumes_oldest_first: Optional[List[float]] = None,
) -> Optional[ScreenedOpportunity]:
    """
    Scores ONE asset from its own real price history. Returns None if
    there isn't enough history for a real technical read — matches
    build_synthetic_technical_report()'s own honest
    None-on-insufficient-data behavior, never a fabricated score for an
    asset with too little data.

    Ranking uses agents.technical_indicators.volatility_normalized_trend_score()
    — NOT the flat-normalized bias_score build_synthetic_technical_report()
    itself produces. Found via live testing: a real cross-asset-class
    screener run using the flat-normalized score came back essentially
    100% volatile growth stocks, structurally, not because those assets
    genuinely had the best opportunities (see this module's own docstring,
    and docs/ARCHITECTURE_OPPORTUNITY_SCREENER.md, for the full account).
    report.confidence is still reused directly — it's independently
    computed from how many of RSI/MACD/SMA had enough data
    (agents/trade_scoring.py: "confidence = 30.0 + 20.0*available_count"),
    entirely unrelated to the flat-normalization bug, so reusing it here
    introduces no inconsistency.

    volumes_oldest_first is OPTIONAL and defaults to None — fully
    backward compatible with every existing caller. When provided,
    agents.technical_indicators.volume_confirmation_ratio()/
    volume_confirmation_multiplier() apply a bounded [0.85, 1.15]
    adjustment to conviction_score: elevated recent volume (a real move
    with real backing, per classical technical analysis going back to Dow
    Theory) boosts it; below-average volume reduces it. Missing or
    unusable volume data (common for some FX pairs — see
    connectors/yahoo_history_connector.py) maps to an EXACTLY neutral 1.0
    multiplier, never a penalty — deliberately, to avoid repeating the
    cross-asset-class fairness mistake found and fixed for trend_score(),
    via a new mechanism.
    """
    technical_input = _price_history_to_technical_input(price_history_oldest_first)
    report = build_synthetic_technical_report(technical_input)
    if report is None:
        return None

    closes_oldest_first = [price for _d, price in price_history_oldest_first]
    if len(closes_oldest_first) < 2:
        return None
    daily_returns = [(closes_oldest_first[i] / closes_oldest_first[i - 1]) - 1.0 for i in range(1, len(closes_oldest_first))]
    asset_vol_pct = annualized_volatility(daily_returns)
    if asset_vol_pct is None or asset_vol_pct <= 0:
        return None  # can't fairly rank this asset without its own real volatility — never guessed

    vol_norm_score = volatility_normalized_trend_score(closes_oldest_first, asset_vol_pct)
    if vol_norm_score is None:
        return None

    volume_multiplier = 1.0
    if volumes_oldest_first is not None:
        volumes_newest_first = list(reversed(volumes_oldest_first))
        volume_ratio = volume_confirmation_ratio(volumes_newest_first)
        volume_multiplier = volume_confirmation_multiplier(volume_ratio)

    conviction = abs(vol_norm_score) * (report.confidence / 100.0) * volume_multiplier
    return ScreenedOpportunity(
        label=label, ticker=ticker, asset_class=asset_class,
        bias_score=round(vol_norm_score, 1), confidence=report.confidence,
        direction="long" if vol_norm_score > 0 else "short",
        conviction_score=round(conviction, 2), annualized_vol_pct=round(asset_vol_pct, 2),
    )


def rank_opportunities(
    opportunities: List[ScreenedOpportunity], min_confidence: float = 40.0, top_n: int = 10,
) -> List[ScreenedOpportunity]:
    """
    Filters to a minimum confidence threshold, then sorts by
    conviction_score descending, returning the top N. Python's sort is
    stable, so assets tied on conviction_score keep their original scan
    order rather than being shuffled — results are reproducible given
    the same input, not randomized on ties.
    """
    usable = [o for o in opportunities if o.confidence >= min_confidence]
    ranked = sorted(usable, key=lambda o: o.conviction_score, reverse=True)
    return ranked[:top_n]


def rank_opportunities_by_class(
    opportunities: List[ScreenedOpportunity], min_confidence: float = 40.0, top_n_per_class: int = 3,
) -> List[ScreenedOpportunity]:
    """
    Same filtering/sorting as rank_opportunities() above, but applied
    INDEPENDENTLY within each asset_class, guaranteeing representation
    across classes rather than letting whichever class currently has the
    strongest signals crowd out every other one.

    Found genuinely necessary via live testing: fixing the real
    cross-asset scoring bias (see this module's docstring) made the
    RANKING fair, but a global top-N over a fair ranking can still
    legitimately come back from one class entirely, if that class simply
    has more, stronger genuinely-trending assets right now than others
    do. That's not a remaining bug — a fair ranking and a diversified one
    are genuinely different goals. This function delivers the second one
    directly, reusing rank_opportunities() for the actual filter/sort
    logic within each class rather than duplicating it.

    Groups by asset_class in the order classes first appear in the input
    (not alphabetized or otherwise reordered) — with the default scan
    order (commodity, fx, crypto, equity), results come back grouped the
    same way, a predictable, reproducible order rather than an arbitrary
    one.
    """
    classes_in_order: List[str] = []
    by_class: dict = {}
    for o in opportunities:
        if o.asset_class not in by_class:
            by_class[o.asset_class] = []
            classes_in_order.append(o.asset_class)
        by_class[o.asset_class].append(o)

    result: List[ScreenedOpportunity] = []
    for asset_class in classes_in_order:
        result.extend(rank_opportunities(by_class[asset_class], min_confidence=min_confidence, top_n=top_n_per_class))
    return result
