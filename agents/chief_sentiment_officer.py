"""
Chief Sentiment Officer.

Per an explicit later restructuring (see
docs/ARCHITECTURE_POSITIONING_SEPARATION.md): institutional desks do not
treat "sentiment" as one blended concept — retail positioning, options
positioning, institutional (COT) positioning, volatility, ETF flows,
market breadth, and news are all DIFFERENT phenomena that should be shown
separately, never averaged into one score, since doing so can hide real
divergences between them.

This agent's earlier design blended News Headline Sentiment with an
OPTIONAL reinterpretation of COT positioning data as "crowd sentiment" —
the same COT dataset Chief Commodity/FX Analyst already reads for a
market, re-read here through a different lens. That blend has been
REMOVED. Chief Sentiment Officer is now purely News Analytics: real RSS
headline sentiment via NewsRssConnector + agents.sentiment_scoring.news_sentiment_score,
nothing else. Institutional (COT) positioning remains fully covered —
just through Chief Commodity Analyst / Chief FX Analyst, its own
dedicated department, never re-blended into a second "sentiment" number
under a different name.

HONEST SCOPE — per the same restructuring, several categories from a
full institutional "Positioning & Market Internals" view have no free
structured live source this platform integrates and are NOT modeled —
not stubbed, not faked, simply absent, the same honest-scope rule applied
everywhere else in this platform:
    - Retail Positioning (OANDA/IG/Myfxbook/FXSSI broker ratios) — all
      proprietary broker feeds; none confirmed free without a funded
      trading account.
    - Options Positioning (Put/Call ratio, options open interest) — no
      documented free API.
    - ETF Flows — SPDR and others publish holdings on their own sites,
      but not through a stable documented free API; would require
      scraping, which this platform doesn't do.
    - MOVE / GVZ / OVX volatility indices — not confirmed to be freely
      available via FRED or any other source this platform integrates
      (VIX itself IS free via FRED and is covered separately — see
      agents/institutional_market_regime.py).
Market Breadth (advance/decline, % above moving averages) IS covered —
see agents/market_breadth.py — computed from the platform's own already-
fetched large-cap equity price history, not a new data source.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score
from models.fundamental_factor import FundamentalFactor, factor_bias_from_score

from .base_agent import BaseAgent
from .sentiment_scoring import news_sentiment_score

CATEGORY = "Sentiment"

# Base confidence for a computable news-sentiment read — deliberately
# modest (not a high-confidence primary driver), matching this platform's
# own convention of keeping Sentiment a supporting signal, not a primary one.
NEWS_CONFIDENCE = 55.0


class ChiefSentimentOfficer(BaseAgent):
    department = "Chief Sentiment Officer"

    def __init__(self, manager, news_key: str, min_quality: float = 60.0):
        """news_key: the key the news RSS dataset was registered under."""
        super().__init__(manager, min_quality)
        self.news_key = news_key

    def required_dataset_keys(self) -> List[str]:
        return [self.news_key]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        evidence: List[str] = []
        catalysts: List[str] = []
        risks: List[str] = []
        factors: List[FundamentalFactor] = []
        bias_score = 0.0
        confidence = 0.0
        risk_level = RiskLevel.HIGH

        news_ds = usable.get(self.news_key)
        if news_ds is not None:
            score = news_sentiment_score(news_ds.payload.get("headlines", []))
            if score is not None:
                bias_score = score
                confidence = NEWS_CONFIDENCE
                risk_level = RiskLevel.MODERATE
                direction = "bullish" if score > 10 else "bearish" if score < -10 else "mixed/neutral"
                evidence.append(
                    f"News sentiment across {news_ds.payload.get('count')} headlines skews "
                    f"{direction} (score {score:+.1f})"
                )
                if score > 10:
                    catalysts.append("Prevailing news flow is constructive")
                elif score < -10:
                    risks.append("Prevailing news flow is negative")
                factors.append(FundamentalFactor(
                    name="News Headline Sentiment",
                    category=CATEGORY,
                    score=round(score, 1),
                    bias=factor_bias_from_score(score),
                    importance_weight=10.0,
                    confidence=NEWS_CONFIDENCE,
                    source=news_ds.source,
                    last_updated=news_ds.provider_timestamp or news_ds.time_collected,
                    notes=[f"{news_ds.payload.get('count')} headlines analyzed"],
                ))

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=bias_from_score(bias_score),
            bias_score=round(bias_score, 1),
            confidence=round(confidence, 1),
            risk_level=risk_level,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=[],
            factor_breakdown=factors,
        )
