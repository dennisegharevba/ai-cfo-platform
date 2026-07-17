"""
Phase 3 demo: register real CFTC COT markets (Gold, Euro FX) and run the
Chief Commodity Analyst and Chief FX Analyst against them.

Run:
    python scripts/demo_commodity_fx_agents.py

Note: like the other demo scripts, this needs outbound network access to
publicreporting.cftc.gov to show real data — no API key required for this
one, though. If unreachable, both agents will correctly report
confidence: 0.0 / risk_level: high rather than fabricating a bias.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MIN_DATA_QUALITY, LOG_LEVEL
from connectors.cot_connector import CotConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_fx_analyst import ChiefFXAnalyst

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

    manager.register("COT_GOLD", primary=CotConnector("GOLD - COMMODITY EXCHANGE INC.", weeks_history=8))
    manager.register("COT_EUR_FX", primary=CotConnector("EURO FX - CHICAGO MERCANTILE EXCHANGE", weeks_history=8))

    print("\n=== AI CFO Platform — Phase 3: Chief Commodity Analyst + Chief FX Analyst demo ===")

    gold_report = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD", min_quality=MIN_DATA_QUALITY).analyze("Gold")
    print_report(gold_report)

    eur_report = ChiefFXAnalyst(manager, cot_key="COT_EUR_FX", min_quality=MIN_DATA_QUALITY).analyze("EUR/USD")
    print_report(eur_report)

    print("\n=== Data integrity status report ===")
    for entry in manager.status_report():
        print(entry)


if __name__ == "__main__":
    main()
