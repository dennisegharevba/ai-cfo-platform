"""
Phase 6 demo: register real Yahoo Finance price history for a small
multi-asset portfolio and run the Chief Risk Officer across it.

Run:
    python scripts/demo_risk_officer.py

Note: like the other demo scripts, this needs outbound network access to
Yahoo Finance. If unreachable, the agent will correctly report
confidence: 0.0 / risk_level: high rather than fabricating an assessment.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MIN_DATA_QUALITY, LOG_LEVEL
from connectors.yahoo_history_connector import YahooHistoryConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_risk_officer import ChiefRiskOfficer
from models.portfolio import Portfolio, Position

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def print_report(report):
    print(f"\n=== {report.department}: {report.asset_or_theme} ===")
    print(f"  Bias:        {report.bias.value}  (score: {report.bias_score:+.1f})  <- always neutral for Risk")
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

    symbols = ["SPY", "AAPL", "GLD", "TLT"]  # broad market, single stock, gold, long treasuries
    for sym in symbols:
        manager.register(f"PRICE_HISTORY_{sym}", primary=YahooHistoryConnector(sym, period="6mo", interval="1d"))

    portfolio = Portfolio(
        name="Demo Portfolio",
        positions=[
            Position(symbol="SPY", quantity=50, asset_class="equity"),
            Position(symbol="AAPL", quantity=20, asset_class="equity"),
            Position(symbol="GLD", quantity=30, asset_class="commodity"),
            Position(symbol="TLT", quantity=25, asset_class="bond"),
        ],
    )

    print("\n=== AI CFO Platform — Phase 6: Chief Risk Officer demo ===")
    report = ChiefRiskOfficer(manager, min_quality=MIN_DATA_QUALITY).analyze_portfolio(portfolio)
    print_report(report)

    print("\n=== Data integrity status report ===")
    for entry in manager.status_report():
        print(entry)


if __name__ == "__main__":
    main()
