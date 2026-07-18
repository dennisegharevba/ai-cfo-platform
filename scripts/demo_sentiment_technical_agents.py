"""
Phase 5 demo: register a real news RSS feed and real Yahoo Finance price
history for SPY, then run the Chief Sentiment Officer and Chief Technical
Officer against them.

Run:
    python scripts/demo_sentiment_technical_agents.py

Note: like the other demo scripts, this needs outbound network access
(to the configured news feed and to Yahoo Finance) to show real data. If
unreachable, both agents will correctly report confidence: 0.0 /
risk_level: high rather than fabricating a bias.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MIN_DATA_QUALITY, LOG_LEVEL, NEWS_RSS_URL
from connectors.news_connector import NewsRssConnector
from connectors.yahoo_history_connector import YahooHistoryConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_sentiment_officer import ChiefSentimentOfficer
from agents.chief_technical_officer import ChiefTechnicalOfficer

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def print_report(report):
    print(f"\n=== {report.department}: {report.asset_or_theme} ===")
    print(f"  Bias:        {report.bias.value}  (score: {report.bias_score:+.1f})")
    print(f"  Confidence:  {report.confidence:.1f}/100")
    print(f"  Risk level:  {report.risk_level.value}")
    for label, items in (("Evidence", report.evidence), ("Catalysts", report.catalysts), ("Risks", report.risks)):
        if items:
            print(f"  {label}:")
            for item in items:
                print(f"    - {item}")
    if report.data_gaps:
        print("  ⚠ Data gaps (excluded from this analysis):")
        for g in report.data_gaps:
            print(f"    - {g}")


def main():
    manager = DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)

    manager.register("MARKET_NEWS", primary=NewsRssConnector(NEWS_RSS_URL))
    manager.register("PRICE_HISTORY_SPY", primary=YahooHistoryConnector("SPY", period="6mo", interval="1d"))

    print("\n=== AI CFO Platform — Phase 5: Chief Sentiment Officer + Chief Technical Officer demo ===")

    sentiment_report = ChiefSentimentOfficer(
        manager, news_key="MARKET_NEWS", min_quality=MIN_DATA_QUALITY
    ).analyze("Broad Market Sentiment")
    print_report(sentiment_report)

    technical_report = ChiefTechnicalOfficer(
        manager, price_key="PRICE_HISTORY_SPY", min_quality=MIN_DATA_QUALITY
    ).analyze("SPY")
    print_report(technical_report)

    print("\n=== Data integrity status report ===")
    for entry in manager.status_report():
        print(entry)


if __name__ == "__main__":
    main()
