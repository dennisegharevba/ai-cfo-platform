"""
Chief Sentiment Officer.

Phase 5 scope:

    - News headline sentiment (primary signal, 100% weight alone, 60% if a
      COT crowd-positioning signal is also supplied) via NewsRssConnector +
      agents.sentiment_scoring.news_sentiment_score
    - Optional: speculative positioning trend, reusing
      agents.positioning_scoring.net_position_trend_score / 
      positioning_extremity_flag from Phase 3 — this is the SAME underlying
      COT dataset the Chief Commodity/FX Analyst reads for a given market,
      just interpreted through a "crowd sentiment" lens here rather than a
      pure directional-bias lens. Reusing the dataset key (not re-fetching)
      means registering the same COT connector once and pointing multiple
      agents at it — the DataIntegrityManager's caching makes this free.

Per the full spec's sentiment coverage (Fear & Greed, ETF/fund flows,
Put/Call ratio, options positioning, retail vs institutional sentiment),
those are natural additional weighted components for a later phase.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .positioning_scoring import net_position_trend_score, positioning_extremity_flag
from .sentiment_scoring import news_sentiment_score

WEIGHT_NEWS_ALONE = 100
WEIGHT_NEWS_WITH_COT = 60
WEIGHT_COT = 40


class ChiefSentimentOfficer(BaseAgent):
    department = "Chief Sentiment Officer"

    def __init__(self, manager, news_key: str, cot_key: Optional[str] = None, min_quality: float = 60.0):
        """
        news_key: the key the news RSS dataset was registered under.
        cot_key: optional — if provided, this market's COT dataset key
        (typically the same one a Chief Commodity/FX Analyst already reads)
        is blended in as a secondary crowd-positioning sentiment signal.
        """
        super().__init__(manager, min_quality)
        self.news_key = news_key
        self.cot_key = cot_key

    def required_dataset_keys(self) -> List[str]:
        keys = [self.news_key]
        if self.cot_key:
            keys.append(self.cot_key)
        return keys

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        evidence: List[str] = []
        catalysts: List[str] = []
        risks: List[str] = []
        component_scores: List[float] = []
        component_weights: List[float] = []
        risk_level = RiskLevel.MODERATE

        news_weight = WEIGHT_NEWS_WITH_COT if self.cot_key else WEIGHT_NEWS_ALONE

        news_ds = usable.get(self.news_key)
        if news_ds is not None:
            score = news_sentiment_score(news_ds.payload.get("headlines", []))
            if score is not None:
                component_scores.append(score)
                component_weights.append(news_weight)
                direction = "bullish" if score > 10 else "bearish" if score < -10 else "mixed/neutral"
                evidence.append(
                    f"News sentiment across {news_ds.payload.get('count')} headlines skews "
                    f"{direction} (score {score:+.1f})"
                )
                if score > 10:
                    catalysts.append("Prevailing news flow is constructive")
                elif score < -10:
                    risks.append("Prevailing news flow is negative")

        if self.cot_key:
            cot_ds = usable.get(self.cot_key)
            if cot_ds is not None:
                history = cot_ds.payload.get("history", [])
                trend = net_position_trend_score(history)
                if trend is not None:
                    component_scores.append(trend)
                    component_weights.append(WEIGHT_COT)
                    direction = "bullish" if trend > 0 else "bearish" if trend < 0 else "neutral"
                    evidence.append(f"Speculative positioning trend adds a {direction} sentiment tilt")

                extremity = positioning_extremity_flag(cot_ds.payload)
                if extremity in ("crowded_long", "crowded_short"):
                    risk_level = RiskLevel.ELEVATED
                    risks.append(
                        f"Positioning is a {extremity.replace('_', ' ')} — crowd sentiment is stretched "
                        f"and vulnerable to a reversal"
                    )

        if component_scores:
            total_weight = sum(component_weights)
            bias_score = sum(s * w for s, w in zip(component_scores, component_weights)) / total_weight
        else:
            bias_score = 0.0

        confidence = 30.0 + (25.0 * len(component_scores))  # 30 base, +25 per usable component (max 80)
        if not usable:
            risk_level = RiskLevel.HIGH
            confidence = 0.0
        elif not component_scores:
            risk_level = RiskLevel.HIGH
            confidence = 0.0
        elif len(usable) < len(self.required_dataset_keys()):
            confidence = max(0.0, confidence - 15.0)

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
        )
