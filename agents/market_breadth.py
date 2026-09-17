"""
Market Breadth.

Per an explicit restructuring (see docs/ARCHITECTURE_POSITIONING_SEPARATION.md):
institutional desks track market breadth (participation across a universe
of names) as its own distinct concept, separate from any single asset's
directional bias and separate from "sentiment." This is a genuinely NEW
capability, but requires no new data source: it's computed entirely from
the SAME PRICE_HISTORY_<TICKER> datasets already fetched for every equity
in the platform's large-cap universe (config.sp500_tickers.LARGE_CAP_TICKERS)
for Chief Risk Fundamentals Officer's volatility/drawdown calculation —
6 months of daily closes, more than enough for a 50-day moving average and
advance/decline. Reusing those exact cached datasets means Market Breadth
adds ZERO additional network requests.

HONEST SCOPE:
    - This is breadth across THIS PLATFORM'S tracked large-cap universe
      (~357 names, see config/sp500_tickers.py's own best-effort caveat),
      NOT the full NYSE/NASDAQ-wide universe real market-breadth data
      providers use, and not literally "the S&P 500" (the ticker list is
      a best-effort approximation, not licensed index membership data).
    - "New highs" / "new lows" are new highs/lows WITHIN THE FETCHED
      WINDOW (~6 months of history), not a true 52-week high/low — labeled
      accordingly throughout, never presented with more precision than
      the underlying data actually supports.
    - Only tickers with usable price history count toward every metric —
      a ticker with insufficient/missing data is excluded entirely, never
      estimated or interpolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .technical_indicators import sma


@dataclass
class BreadthResult:
    universe_size: int              # how many tickers were requested
    usable_count: int               # how many actually had usable price history
    advancers: int = 0
    decliners: int = 0
    unchanged: int = 0
    pct_above_50dma: Optional[float] = None
    sma_computable_count: int = 0   # how many tickers had enough history for a 50-day SMA
    new_highs: int = 0
    new_lows: int = 0
    window_days: int = 0            # the actual fetched-history window used for new-high/low, in trading days

    @property
    def advance_decline_ratio(self) -> Optional[float]:
        """None if there's nothing to compute a ratio from at all."""
        if self.advancers == 0 and self.decliners == 0:
            return None
        if self.decliners == 0:
            return float("inf")
        return round(self.advancers / self.decliners, 2)

    def to_dict(self) -> dict:
        return {
            "universe_size": self.universe_size,
            "usable_count": self.usable_count,
            "advancers": self.advancers,
            "decliners": self.decliners,
            "unchanged": self.unchanged,
            "advance_decline_ratio": self.advance_decline_ratio,
            "pct_above_50dma": self.pct_above_50dma,
            "sma_computable_count": self.sma_computable_count,
            "new_highs": self.new_highs,
            "new_lows": self.new_lows,
            "window_days": self.window_days,
        }


def compute_breadth(price_histories: Dict[str, List[dict]]) -> BreadthResult:
    """
    price_histories: ticker -> newest-first history list, the same shape
    connectors.yahoo_history_connector.YahooHistoryConnector returns
    (each row a dict with at least a "close" key).

    Tickers with fewer than 2 usable closes are excluded entirely from
    every metric (never estimated) — universe_size counts what was
    requested, usable_count counts what actually contributed.
    """
    universe_size = len(price_histories)
    usable_count = 0
    advancers = decliners = unchanged = 0
    above_50dma_count = 0
    sma_computable_count = 0
    new_highs = new_lows = 0
    window_days = 0

    for ticker, history in price_histories.items():
        closes_newest_first = [row["close"] for row in history if isinstance(row, dict) and "close" in row]
        if len(closes_newest_first) < 2:
            continue
        usable_count += 1
        window_days = max(window_days, len(closes_newest_first))

        latest = closes_newest_first[0]
        previous = closes_newest_first[1]
        if latest > previous:
            advancers += 1
        elif latest < previous:
            decliners += 1
        else:
            unchanged += 1

        closes_oldest_first = list(reversed(closes_newest_first))
        sma50 = sma(closes_oldest_first, 50)
        if sma50 is not None:
            sma_computable_count += 1
            if latest > sma50:
                above_50dma_count += 1

        if latest >= max(closes_newest_first):
            new_highs += 1
        if latest <= min(closes_newest_first):
            new_lows += 1

    pct_above_50dma = (
        round((above_50dma_count / sma_computable_count) * 100, 1) if sma_computable_count > 0 else None
    )

    return BreadthResult(
        universe_size=universe_size,
        usable_count=usable_count,
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        pct_above_50dma=pct_above_50dma,
        sma_computable_count=sma_computable_count,
        new_highs=new_highs,
        new_lows=new_lows,
        window_days=window_days,
    )
