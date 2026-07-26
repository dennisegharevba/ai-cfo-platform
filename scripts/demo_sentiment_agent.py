"""
Phase 5 demo (Chief Sentiment Officer only — Chief Technical Officer was
later removed from the platform's main scoring pipeline entirely, per
user request; see docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md. This
file replaces the original scripts/demo_sentiment_technical_agents.py,
which covered both departments).

Registers a real news RSS feed and runs the Chief Sentiment Officer
against it.

Run:
    python scripts/demo_sentiment_agent.py

Note: like the other demo scripts, this needs outbound network access
(to the configured news feed) to show real data. If unreachable, the
agent will correctly report confidence: 0.0 / risk_level: high rather
than fabricating a bias.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MIN_DATA_QUALITY, LOG_LEVEL, NEWS_RSS_URL
from connectors.news_connector import NewsRssConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_sentiment_officer import ChiefSentimentOfficer

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

    print("\n=== AI CFO Platform — Chief Sentiment Officer demo ===")

    sentiment_report = ChiefSentimentOfficer(
        manager, news_key="MARKET_NEWS", min_quality=MIN_DATA_QUALITY
    ).analyze("Broad Market Sentiment")
    print_report(sentiment_report)

    print("\n=== Data integrity status report ===")
    for entry in manager.status_report():
        print(entry)


if __name__ == "__main__":
    main()
