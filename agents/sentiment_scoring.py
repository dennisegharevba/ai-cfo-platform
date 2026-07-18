"""
News headline sentiment scoring for the Chief Sentiment Officer.

Deliberately a small, curated keyword lexicon rather than an ML sentiment
model — every score this produces can be explained by pointing at which
words matched, consistent with the rest of this platform's philosophy of
auditable, one-sentence-explainable scoring.
"""

from __future__ import annotations

from typing import List, Optional

BULLISH_KEYWORDS = [
    "rally", "surge", "soar", "jump", "gain", "gains", "record high",
    "beat", "beats", "upgrade", "upgraded", "optimis", "rebound",
    "recovery", "strong", "bullish", "outperform", "boom",
]

BEARISH_KEYWORDS = [
    "selloff", "sell-off", "plunge", "slump", "crash", "tumble", "slide",
    "recession", "downgrade", "downgraded", "weak", "bearish", "fears",
    "losses", "default", "layoffs", "bankruptcy", "collapse",
]


def news_sentiment_score(headlines: List[str]) -> Optional[float]:
    """
    Count bullish vs. bearish keyword matches across all headlines
    (case-insensitive substring match), net them, and normalize to
    -100..+100. A net keyword count equal to half the headline count is
    treated as a "strong" skew — e.g. 10 headlines with a net of +5
    bullish-minus-bearish matches scores +100.

    Returns None if the headline list is empty.
    """
    if not headlines:
        return None

    bullish_count = 0
    bearish_count = 0
    for headline in headlines:
        low = headline.lower()
        bullish_count += sum(1 for kw in BULLISH_KEYWORDS if kw in low)
        bearish_count += sum(1 for kw in BEARISH_KEYWORDS if kw in low)

    net = bullish_count - bearish_count
    denom = max(1.0, len(headlines) * 0.5)
    return max(-100.0, min(100.0, (net / denom) * 100))
