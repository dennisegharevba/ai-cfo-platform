"""
Chief Asset Risk Officer — per-ASSET risk (distinct from
agents/chief_risk_officer.py, which is per-PORTFOLIO: concentration, VaR,
drawdown, correlation across positions someone actually holds).

Per the Institutional Trade Decision Engine spec, the per-asset Risk Score
(20% weight of the Overall Score, section 1) covers: upcoming news/event
risk, crowded positioning, commercial/speculative divergence, volatility
and ATR expansion, liquidity risk, and weekend gap risk.

Inputs, all OPTIONAL individually (an asset without COT data, e.g. a single
stock, still gets a risk read from price action + news alone; missing
inputs degrade confidence rather than blocking the read — same philosophy
as every other agent in this platform):
    - price_key  -> YahooHistoryConnector-shaped payload (ATR expansion,
                    weekend-gap risk, realized volatility)
    - cot_key    -> CotConnector-shaped payload (crowded positioning via
                    agents.positioning_scoring.positioning_extremity_flag,
                    commercial/speculative divergence — reusing the exact
                    same functions agents/positioning_agent_base.py already
                    uses, so "crowded" and "diverging" mean the same thing
                    everywhere in this platform)
    - news_key   -> NewsRssConnector-shaped payload (event/news risk via a
                    small curated keyword lexicon, same auditable-lexicon
                    philosophy as agents/sentiment_scoring.py)

Documented Phase-12 simplification (not hidden, matching this platform's
convention — see chief_risk_officer.py's own documented simplification):
CROSS-ASSET correlation risk is intentionally NOT computed here. That
requires simultaneous multi-asset return series the way
agents/chief_risk_officer.py already does for a portfolio's actual
holdings; a single-asset agent has nothing to correlate against. If/when
open positions exist (models/open_trade.py), a later phase should reuse
agents/risk_calculations.py's pearson_correlation against the other
currently-open assets.

Like agents/chief_risk_officer.py, this agent takes no directional view —
bias/bias_score are always neutral/0.0. Its risk_level and risks list are
the actual product; agents/trade_scoring.py converts risk_level + the
number of distinct flagged risks into the 0-100 Risk Score the Trade
Decision Engine uses (higher score = LOWER risk, per spec section 1).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, Bias, RiskLevel

from .base_agent import BaseAgent
from .positioning_scoring import net_position_trend_score, positioning_extremity_flag
from .technical_indicators import atr, atr_expansion_pct
from .risk_severity import worse_risk_level as _worse

ATR_EXPANSION_ELEVATED_PCT = 25.0
ATR_EXPANSION_HIGH_PCT = 50.0

# A weekend gap is measured as the % move between Friday's close and the
# next trading session's open-equivalent (here: the next bar's high/low
# midpoint, since intraday-open isn't part of this connector's payload) —
# a large gap means a position held over the weekend was exposed to a move
# that couldn't be reacted to intraday.
WEEKEND_GAP_ELEVATED_PCT = 1.5
WEEKEND_GAP_HIGH_PCT = 3.0

EVENT_RISK_KEYWORDS = [
    "fomc", "fed decision", "rate decision", "cpi", "nonfarm payroll", "nfp",
    "jobs report", "ecb", "boe", "boj", "central bank", "rate hike", "rate cut",
    "opec", "earnings", "gdp release", "employment report", "press conference",
]


def _closes_highs_lows_oldest_first(history: List[dict]) -> tuple[List[float], List[float], List[float]]:
    closes, highs, lows = [], [], []
    for row in reversed(history):  # connector convention: newest-first -> reverse
        try:
            closes.append(float(row["close"]))
            highs.append(float(row.get("high", row["close"])))
            lows.append(float(row.get("low", row["close"])))
        except (KeyError, TypeError, ValueError):
            continue
    return highs, lows, closes


def _weekend_gap_pct(history: List[dict]) -> Optional[float]:
    """
    Scan the most recent ~10 trading days (newest-first, as stored) for the
    largest single-session gap that spans a weekend (a >=2-day jump in the
    ISO date), measured as |this bar's low-high midpoint vs prior bar's
    midpoint| / prior midpoint. Returns None if dates can't be parsed.
    """
    from datetime import date as _date

    gaps = []
    window = history[:10]
    for i in range(len(window) - 1):
        try:
            d_recent = _date.fromisoformat(window[i]["date"][:10])
            d_prior = _date.fromisoformat(window[i + 1]["date"][:10])
            mid_recent = (float(window[i]["high"]) + float(window[i]["low"])) / 2
            mid_prior = (float(window[i + 1]["high"]) + float(window[i + 1]["low"])) / 2
        except (KeyError, TypeError, ValueError):
            continue

        day_gap = (d_recent - d_prior).days
        if day_gap >= 2 and mid_prior != 0:  # spans at least one non-trading day (weekend/holiday)
            gaps.append(abs(mid_recent - mid_prior) / mid_prior * 100)

    return max(gaps) if gaps else None


def _event_risk_headlines(headlines: List[str]) -> List[str]:
    matched = []
    for h in headlines:
        h_lower = h.lower()
        if any(kw in h_lower for kw in EVENT_RISK_KEYWORDS):
            matched.append(h)
    return matched


class ChiefAssetRiskOfficer(BaseAgent):
    department = "Chief Asset Risk Officer"

    def __init__(
        self, manager, price_key: Optional[str] = None, cot_key: Optional[str] = None,
        news_key: Optional[str] = None, min_quality: float = 60.0,
    ):
        super().__init__(manager, min_quality)
        self.price_key = price_key
        self.cot_key = cot_key
        self.news_key = news_key

    def required_dataset_keys(self) -> List[str]:
        return [k for k in (self.price_key, self.cot_key, self.news_key) if k is not None]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        evidence: List[str] = []
        catalysts: List[str] = []
        risks: List[str] = []
        risk_level = RiskLevel.MODERATE
        signals_used = 0

        # --- Volatility / ATR expansion / weekend gap (from price history) ---
        price_ds = usable.get(self.price_key) if self.price_key else None
        if price_ds is not None:
            history = price_ds.payload.get("history", [])
            highs, lows, closes = _closes_highs_lows_oldest_first(history)

            expansion = atr_expansion_pct(highs, lows, closes)
            if expansion is not None:
                signals_used += 1
                evidence.append(f"ATR(14) has changed {expansion:+.1f}% vs. 14 bars ago")
                if expansion >= ATR_EXPANSION_HIGH_PCT:
                    risk_level = _worse(risk_level, RiskLevel.HIGH)
                    risks.append(f"ATR expansion ({expansion:+.1f}%) — volatility is sharply increasing")
                elif expansion >= ATR_EXPANSION_ELEVATED_PCT:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append(f"ATR expansion ({expansion:+.1f}%) — volatility is elevated and rising")
                elif expansion <= -ATR_EXPANSION_ELEVATED_PCT:
                    catalysts.append(f"ATR contraction ({expansion:+.1f}%) — volatility is compressing")

            gap = _weekend_gap_pct(history)
            if gap is not None:
                signals_used += 1
                evidence.append(f"Largest recent weekend/holiday gap was {gap:.1f}%")
                if gap >= WEEKEND_GAP_HIGH_PCT:
                    risk_level = _worse(risk_level, RiskLevel.HIGH)
                    risks.append(f"Weekend/holiday gap risk is high (recent gap of {gap:.1f}%)")
                elif gap >= WEEKEND_GAP_ELEVATED_PCT:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append(f"Weekend/holiday gap risk is elevated (recent gap of {gap:.1f}%)")

        # --- Crowded positioning + commercial/speculative divergence (from COT) ---
        cot_ds = usable.get(self.cot_key) if self.cot_key else None
        if cot_ds is not None:
            cot_history = cot_ds.payload.get("history", [])
            signals_used += 1

            extremity = positioning_extremity_flag(cot_ds.payload)
            if extremity == "crowded_long":
                risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                risks.append("Speculative positioning is a crowded long — reversal risk")
            elif extremity == "crowded_short":
                risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                risks.append("Speculative positioning is a crowded short — short-covering risk")

            spec_trend = net_position_trend_score(cot_history, "noncomm_long", "noncomm_short")
            comm_trend = net_position_trend_score(cot_history, "comm_long", "comm_short")
            if spec_trend is not None and comm_trend is not None:
                if spec_trend * comm_trend < 0 and abs(spec_trend) > 20 and abs(comm_trend) > 20:
                    risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                    risks.append("Commercial vs. speculative positioning is diverging — trend exhaustion risk")
                    evidence.append(
                        f"Speculative trend {spec_trend:+.1f} vs. commercial trend {comm_trend:+.1f} — diverging"
                    )

        # --- Event / news risk (from headlines) ---
        news_ds = usable.get(self.news_key) if self.news_key else None
        if news_ds is not None:
            signals_used += 1
            headlines = news_ds.payload.get("headlines", [])
            event_headlines = _event_risk_headlines(headlines)
            if event_headlines:
                risk_level = _worse(risk_level, RiskLevel.ELEVATED)
                risks.append(f"{len(event_headlines)} headline(s) reference upcoming macro/event catalysts")
                evidence.append("Event-risk headlines: " + "; ".join(event_headlines[:3]))

        if signals_used == 0:
            risk_level = RiskLevel.HIGH
            risks.append("No price, positioning, or news data was usable — risk cannot be properly assessed")

        confidence = min(90.0, 30.0 * signals_used)

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=Bias.NEUTRAL,  # this desk assesses risk, not direction — matches chief_risk_officer.py
            bias_score=0.0,
            confidence=round(confidence, 1),
            risk_level=risk_level,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=[],
        )
