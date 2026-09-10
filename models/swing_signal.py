"""
SwingSignal: the output of agents/swing_signal.py — a swing-trading-specific
reading of a COT positioning reversal, cross-checked against the platform's
broad market news sentiment.

Kept as its own model (not bolted onto models.report.AgentReport) for the
same reason models/trade_decision.py is its own model rather than extra
fields on models/strategy_report.py: this answers a different question
("is a swing entry setting up right now") than AgentReport's general
bias/confidence shape, and keeping it separate makes that boundary visible
to a type-checker, not just a convention to remember. See
agents/swing_signal.py for exactly how each field is produced, and
docs/ARCHITECTURE_SWING_SIGNAL.md for the full design account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class SwingDirection(str, Enum):
    BEARISH_TURN = "bearish_turn"   # Non-Commercial positioning turning DOWN against the trend
    BULLISH_TURN = "bullish_turn"   # Non-Commercial positioning turning UP against the trend


class NewsAlignment(str, Enum):
    CONFIRMS = "confirms"        # broad market news sentiment leans the same direction as the turn
    CONTRADICTS = "contradicts"  # broad market news sentiment leans the opposite direction
    NEUTRAL = "neutral"          # news sentiment is genuinely mixed/near-zero — takes no side
    NO_DATA = "no_data"          # no market news sentiment score was available this cycle


SWING_DIRECTION_LABELS = {
    SwingDirection.BEARISH_TURN: "turning BEARISH",
    SwingDirection.BULLISH_TURN: "turning BULLISH",
}

NEWS_ALIGNMENT_LABELS = {
    NewsAlignment.CONFIRMS: "confirms",
    NewsAlignment.CONTRADICTS: "contradicts",
    NewsAlignment.NEUTRAL: "is mixed/neutral on",
    NewsAlignment.NO_DATA: "has no read on",
}


@dataclass
class SwingSignal:
    asset_or_theme: str
    direction: SwingDirection
    weekly_change: float                    # contracts, this week's move (see agents.speculative_positioning_analysis.latest_weekly_change)
    trend_score: float                       # the broader multi-week trend this move is opposing (-100..+100)
    percentile: Optional[float]              # where the CURRENT reading sits in the fetched window (0-100)
    extreme_label: Optional[str]             # "extreme_bullish" / "extreme_bearish" / None
    news_sentiment_score: Optional[float]    # broad market news sentiment, -100..+100, or None if unavailable
    news_alignment: NewsAlignment
    confidence: float                        # 0-100
    evidence: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def headline(self) -> str:
        """One-line, plain-English summary — for a Telegram alert or a compact dashboard row."""
        emoji = "🔻" if self.direction == SwingDirection.BEARISH_TURN else "🔺"
        direction_label = SWING_DIRECTION_LABELS[self.direction]
        alignment_label = NEWS_ALIGNMENT_LABELS[self.news_alignment]
        return (
            f"{emoji} {self.asset_or_theme}: COT positioning is {direction_label} against the "
            f"established trend — broad market news {alignment_label} it (confidence {self.confidence:.0f}/100)"
        )

    def to_dict(self) -> dict:
        return {
            "asset_or_theme": self.asset_or_theme,
            "direction": self.direction.value,
            "weekly_change": self.weekly_change,
            "trend_score": self.trend_score,
            "percentile": self.percentile,
            "extreme_label": self.extreme_label,
            "news_sentiment_score": self.news_sentiment_score,
            "news_alignment": self.news_alignment.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "generated_at": self.generated_at.isoformat(),
        }
