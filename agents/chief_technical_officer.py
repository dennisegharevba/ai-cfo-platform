"""
Chief Technical Officer.

Phase 5 scope: one agent instance per ticker, scoring three classic
technical components against daily closing prices (via YahooHistoryConnector):

    - RSI(14)         20% weight  — momentum; also flags overbought/oversold as risk
    - MACD histogram  40% weight  — trend acceleration/deceleration
    - SMA(20/50) trend 40% weight — is price in a sustained up/downtrend

Per the spec, this department's job is to "confirm or reject the
fundamental thesis" — that reconciliation is the Chief Strategy Officer's
job (Phase 7), which will read this agent's AgentReport alongside every
fundamental department's. This agent only produces its own independent
technical read; it does not know about or adjust for any other department's
conclusion.

Per the full spec's technical coverage (Market Structure, Elliott Wave,
Wyckoff, Volume Profile, Anchored VWAP, OBV, ATR, Fair Value Gaps, Liquidity,
Order Blocks, multi-timeframe analysis), RSI/MACD/SMA-trend are the starting
subset — additional weighted components slot in later without changing this
agent's shape.
"""

from __future__ import annotations

from typing import Dict, List

from core.dataset import Dataset
from models.report import AgentReport, RiskLevel, bias_from_score

from .base_agent import BaseAgent
from .technical_indicators import rsi, macd_histogram, trend_score

WEIGHT_RSI = 20
WEIGHT_MACD = 40
WEIGHT_TREND = 40

RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0


def _closes_oldest_first(history: List[dict]) -> List[float]:
    """Connectors store history newest-first; indicator math needs oldest-first."""
    values = []
    for row in reversed(history):
        try:
            values.append(float(row["close"]))
        except (KeyError, TypeError, ValueError):
            continue
    return values


class ChiefTechnicalOfficer(BaseAgent):
    department = "Chief Technical Officer"

    def __init__(self, manager, price_key: str, min_quality: float = 60.0):
        """
        price_key: the key this ticker's daily-close history was registered
        under in the DataIntegrityManager, e.g. "PRICE_HISTORY_AAPL".
        """
        super().__init__(manager, min_quality)
        self.price_key = price_key

    def required_dataset_keys(self) -> List[str]:
        return [self.price_key]

    def _build_report(self, usable: Dict[str, Dataset], asset_or_theme: str) -> AgentReport:
        evidence: List[str] = []
        catalysts: List[str] = []
        risks: List[str] = []
        component_scores: List[float] = []
        component_weights: List[float] = []
        risk_level = RiskLevel.MODERATE

        ds = usable.get(self.price_key)
        if ds is not None:
            closes = _closes_oldest_first(ds.payload.get("history", []))

            rsi_value = rsi(closes, period=14)
            if rsi_value is not None:
                rsi_score = max(-100.0, min(100.0, (rsi_value - 50.0) * 2))
                component_scores.append(rsi_score)
                component_weights.append(WEIGHT_RSI)
                evidence.append(f"RSI(14) is {rsi_value:.1f}")
                if rsi_value >= RSI_OVERBOUGHT:
                    risk_level = RiskLevel.ELEVATED
                    risks.append(f"RSI({rsi_value:.1f}) is overbought — vulnerable to a pullback")
                elif rsi_value <= RSI_OVERSOLD:
                    risk_level = RiskLevel.ELEVATED
                    risks.append(f"RSI({rsi_value:.1f}) is oversold — vulnerable to a bounce")

            macd_hist = macd_histogram(closes, fast=12, slow=26, signal=9)
            if macd_hist is not None and ds.payload.get("latest_close"):
                # Normalize the raw price-unit histogram by price level so it's
                # comparable across assets of very different price magnitudes.
                latest_close = float(ds.payload["latest_close"])
                pct_of_price = (macd_hist / latest_close) * 100 if latest_close else 0.0
                macd_score = max(-100.0, min(100.0, (pct_of_price / 1.0) * 100))
                component_scores.append(macd_score)
                component_weights.append(WEIGHT_MACD)
                direction = "accelerating higher" if macd_hist > 0 else "accelerating lower" if macd_hist < 0 else "flat"
                evidence.append(f"MACD histogram is {direction} ({macd_hist:+.4f})")
                if macd_hist > 0:
                    catalysts.append("Positive MACD histogram shows upward momentum building")
                elif macd_hist < 0:
                    risks.append("Negative MACD histogram shows downward momentum building")

            trend = trend_score(closes, short=20, long=50)
            if trend is not None:
                component_scores.append(trend)
                component_weights.append(WEIGHT_TREND)
                direction = "an uptrend" if trend > 0 else "a downtrend" if trend < 0 else "no clear trend"
                evidence.append(f"Price structure shows {direction} (20 SMA vs 50 SMA)")
                if trend > 0:
                    catalysts.append("Price is in a sustained uptrend (20 SMA above 50 SMA)")
                elif trend < 0:
                    risks.append("Price is in a sustained downtrend (20 SMA below 50 SMA)")

        if component_scores:
            total_weight = sum(component_weights)
            bias_score = sum(s * w for s, w in zip(component_scores, component_weights)) / total_weight
        else:
            bias_score = 0.0

        confidence = 30.0 + (20.0 * len(component_scores))  # 30 base, +20 per usable component (max 90)
        if ds is None:
            risk_level = RiskLevel.HIGH
            confidence = 0.0
        elif not component_scores:
            risk_level = RiskLevel.HIGH
            confidence = 0.0

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
