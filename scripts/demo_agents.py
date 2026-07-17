"""
Phase 2 demo: register the real FRED series the Chief Macro Officer and
Chief Bond Strategist need, run both agents, and print their reports.

Run:
    python scripts/demo_agents.py

Note: like scripts/demo_refresh.py, this needs a real FRED_API_KEY in .env
and outbound network access to stlouisfed.org to show real data. If either
is missing, the agents will correctly report degraded/zero-confidence
results rather than fabricating a bias — see docs/ARCHITECTURE.md.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import FRED_API_KEY, MIN_DATA_QUALITY, LOG_LEVEL
from connectors.fred_connector import FredConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_macro_officer import ChiefMacroOfficer, KEY_CPI, KEY_UNRATE
from agents.chief_bond_strategist import ChiefBondStrategist, KEY_DGS10, KEY_DGS2

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def print_report(report):
    print(f"\n=== {report.department}: {report.asset_or_theme} ===")
    print(f"  Bias:        {report.bias.value}  (score: {report.bias_score:+.1f})")
    print(f"  Confidence:  {report.confidence:.1f}/100")
    print(f"  Risk level:  {report.risk_level.value}")
    if report.evidence:
        print("  Evidence:")
        for e in report.evidence:
            print(f"    - {e}")
    if report.catalysts:
        print("  Catalysts:")
        for c in report.catalysts:
            print(f"    - {c}")
    if report.risks:
        print("  Risks:")
        for r in report.risks:
            print(f"    - {r}")
    if report.data_gaps:
        print("  ⚠ Data gaps (excluded from this analysis):")
        for g in report.data_gaps:
            print(f"    - {g}")


def main():
    manager = DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)

    manager.register(KEY_CPI, primary=FredConnector(series_id="CPIAUCSL", api_key=FRED_API_KEY))
    manager.register(KEY_UNRATE, primary=FredConnector(series_id="UNRATE", api_key=FRED_API_KEY))
    manager.register(KEY_DGS10, primary=FredConnector(series_id="DGS10", api_key=FRED_API_KEY))
    manager.register(KEY_DGS2, primary=FredConnector(series_id="DGS2", api_key=FRED_API_KEY))

    print("\n=== AI CFO Platform — Phase 2: Chief Macro Officer + Chief Bond Strategist demo ===")

    macro_report = ChiefMacroOfficer(manager, min_quality=MIN_DATA_QUALITY).analyze("US Macro Outlook")
    print_report(macro_report)

    bond_report = ChiefBondStrategist(manager, min_quality=MIN_DATA_QUALITY).analyze("US Treasuries")
    print_report(bond_report)

    print("\n=== Data integrity status report ===")
    for entry in manager.status_report():
        print(entry)


if __name__ == "__main__":
    main()
