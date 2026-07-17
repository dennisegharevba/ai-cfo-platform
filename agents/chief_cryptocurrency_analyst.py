"""
Chief Cryptocurrency Analyst.

Phase 4 scope: one agent instance per symbol (e.g. BTCUSDT, ETHUSDT), scoring:

    - funding rate  (primary signal, 60% weight): sign/magnitude of the
      perpetual funding rate as a direct read on positioning dominance
    - open interest trend (secondary, 40% weight): confirms how much
      conviction (rising OI) or unwind (falling OI) is behind that positioning

An extreme funding rate (see agents/crypto_scoring.py) is flagged as a
crowded long/short trade and elevates risk_level, independent of bias
direction — mirroring the Chief Commodity/FX Analysts' COT-extremity flag
(Phase 3), but using crypto's own native "crowding" metric instead of
COT's percent-of-open-interest measure.

Per the full spec's crypto coverage (liquidation heatmaps, ETF flows,
on-chain metrics, stablecoin flows, exchange reserves, whale activity...),
those are the natural next weighted components for a later phase.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .crypto_scoring import funding_rate_bias_score, funding_rate_extremity_flag
from .trend_scoring import series_trend_score

WEIGHT_FUNDING = 60
WEIGHT_OPEN_INTEREST = 40


class ChiefCryptocurrencyAnalyst(BaseAgent):
    department = "Chief Cryptocurrency Analyst"

    def __init__(self, manager, crypto_key: str, min_quality: float = 60.0):
        """
        crypto_key: the key this symbol's Binance futures dataset was
        registered under in the DataIntegrityManager, e.g. "CRYPTO_BTCUSDT".
        """
        super().__init__(manager, min_quality)
        self.crypto_key = crypto_key

    def required_dataset_keys(self) -> List[str]:
        return [self.crypto_key]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        evidence: List[str] = []
        catalysts: List[str] = []
        risks: List[str] = []
        component_scores: List[float] = []
        component_weights: List[float] = []
        risk_level = RiskLevel.MODERATE

        ds = usable.get(self.crypto_key)
        if ds is not None:
            funding_rate = ds.payload.get("latest_funding_rate")
            if funding_rate is not None:
                funding_score = funding_rate_bias_score(funding_rate)
                component_scores.append(funding_score)
                component_weights.append(WEIGHT_FUNDING)
                direction = "positive (longs paying a premium)" if funding_rate > 0 else \
                    "negative (shorts paying a premium)" if funding_rate < 0 else "flat"
                evidence.append(f"Funding rate is {direction}: {funding_rate:+.5f}")
                if funding_rate > 0:
                    catalysts.append("Positive funding reflects bullish positioning dominance")
                elif funding_rate < 0:
                    risks.append("Negative funding reflects bearish positioning dominance")

                extremity = funding_rate_extremity_flag(funding_rate)
                if extremity == "crowded_long":
                    risk_level = RiskLevel.ELEVATED
                    risks.append("Funding rate is extremely positive — a crowded long, vulnerable to a long squeeze")
                elif extremity == "crowded_short":
                    risk_level = RiskLevel.ELEVATED
                    risks.append("Funding rate is extremely negative — a crowded short, vulnerable to a short squeeze")

            oi_score = series_trend_score(ds.payload.get("history", []), lower_is_bullish=False, value_key="open_interest")
            if oi_score is not None:
                component_scores.append(oi_score)
                component_weights.append(WEIGHT_OPEN_INTEREST)
                direction = "rising" if oi_score > 0 else "falling" if oi_score < 0 else "flat"
                evidence.append(f"Open interest is {direction} over the fetched window")

        if component_scores:
            total_weight = sum(component_weights)
            bias_score = sum(s * w for s, w in zip(component_scores, component_weights)) / total_weight
        else:
            bias_score = 0.0

        confidence = 40.0 + (20.0 * len(component_scores))  # 40 base, +20 per usable component (max 80)
        if ds is None:
            risk_level = RiskLevel.HIGH
            confidence = 0.0
        elif len(usable) < len(self.required_dataset_keys()):
            risk_level = RiskLevel.ELEVATED if risk_level == RiskLevel.MODERATE else risk_level
            confidence = max(0.0, confidence - 20.0)

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
