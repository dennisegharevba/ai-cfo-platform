"""
Diagnostic tool: tests several candidate news RSS feed URLs side by side
and shows real headlines from each, tagged with any sentiment keyword
matches. Built specifically because a live run of Chief Sentiment Officer
showed the CONFIGURED DEFAULT feed (MarketWatch "top stories") returning
10 of 10 headlines that were personal-finance advice-column content
("should I pay off my mortgage?", "how do I care for my elderly
relative?") rather than genuine market/economic news — not a keyword-list
problem, a feed-content problem.

HONEST CAVEAT: the candidate URLs below are best-effort, assembled from
general knowledge of commonly-used financial news RSS feeds — NOT
verified against live responses from this development environment (no
network access here). Some may be dead, redirected, or blocked. Run this
with real network access to see which ones actually work AND actually
return market-relevant content.

Run:
    python scripts/debug_news_feeds.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connectors.news_connector import NewsRssConnector
from agents.sentiment_scoring import BULLISH_KEYWORDS, BEARISH_KEYWORDS

# Best-effort candidates — see this module's docstring. The current
# config/settings.py default (marketwatch/topstories) is included first
# for direct comparison against the alternatives.
CANDIDATE_FEEDS = {
    "MarketWatch Top Stories (current default)": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "MarketWatch MarketPulse": "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    "CNBC Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "Yahoo Finance News": "https://finance.yahoo.com/news/rssindex",
}


def main():
    for label, url in CANDIDATE_FEEDS.items():
        print(f"\n{'=' * 70}")
        print(f"{label}")
        print(f"{url}")
        print("=" * 70)
        try:
            payload, provider_ts = NewsRssConnector(url, max_headlines=10).fetch()
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        headlines = payload.get("headlines", [])
        if not headlines:
            print("  No headlines returned.")
            continue

        bull_total = bear_total = 0
        for h in headlines[:10]:
            low = h.lower()
            bull_hits = [kw for kw in BULLISH_KEYWORDS if kw in low]
            bear_hits = [kw for kw in BEARISH_KEYWORDS if kw in low]
            bull_total += len(bull_hits)
            bear_total += len(bear_hits)
            tag = f"[BULLISH: {bull_hits}]" if bull_hits else f"[BEARISH: {bear_hits}]" if bear_hits else "[no match]"
            print(f"  - {h}  {tag}")

        print(f"\n  Totals: {bull_total} bullish keyword hits, {bear_total} bearish keyword hits across {len(headlines[:10])} headlines")


if __name__ == "__main__":
    main()
