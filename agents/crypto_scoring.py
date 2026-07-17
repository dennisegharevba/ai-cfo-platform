"""
Scoring helpers for crypto derivatives positioning data (currently: Chief
Cryptocurrency Analyst only — kept in its own module rather than
agents/positioning_scoring.py since the underlying signal, funding rate, is
a fundamentally different metric from COT net positioning even though both
represent "crowd positioning").
"""

from __future__ import annotations

from typing import Optional

# A funding rate this large (in either direction) is treated as a "strong"
# signal (+/-100). Perpetual funding rates are typically quoted per 8h and
# are usually well under 0.05% (0.0005) outside of extreme conditions.
FUNDING_RATE_NORMALIZATION = 0.0005

# Beyond this magnitude, funding is considered a "crowded" trade — traders
# are paying a steep premium to stay positioned, a classic setup for a
# squeeze in the opposite direction.
FUNDING_RATE_EXTREME_THRESHOLD = 0.001


def funding_rate_bias_score(funding_rate: float) -> float:
    """
    Positive funding rate -> longs are paying shorts a premium -> bullish
    positioning dominance. Negative -> shorts paying longs -> bearish
    positioning dominance. Normalized to -100..+100.
    """
    return max(-100.0, min(100.0, (funding_rate / FUNDING_RATE_NORMALIZATION) * 100))


def funding_rate_extremity_flag(funding_rate: float, threshold: float = FUNDING_RATE_EXTREME_THRESHOLD) -> Optional[str]:
    """Flag an unusually large funding rate as a crowded long/short trade."""
    if funding_rate > threshold:
        return "crowded_long"
    if funding_rate < -threshold:
        return "crowded_short"
    return None
