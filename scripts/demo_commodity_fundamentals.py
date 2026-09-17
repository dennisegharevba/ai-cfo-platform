"""
Demo: Chief Commodity Fundamentals Officer, run alongside the existing
COT-based Chief Commodity Analyst for the same commodity — showing both
department reports plus how Chief Strategy Officer weights them (per
docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md: Commodity Fundamentals
gets the default 1.0 weight, Chief Commodity Analyst gets 0.4 — COT stays
supporting-only, fundamentals stay primary).

Also demonstrates Gold's precious-metals fundamentals (real yields, Dollar
Index, Fed Funds Rate — the same US-Dollar-related data driving USD
itself, since Gold is priced in dollars — see
docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md), which reuse Chief Macro
Officer's own shared FRED keys rather than fetching the same series again.

Run:
    python scripts/demo_commodity_fundamentals.py

Notes:
    - The EIA connector needs a free EIA_API_KEY in .env
      (https://www.eia.gov/opendata/register.php)
    - Gold's factors need FRED_API_KEY (shared with Chief Macro Officer)
    - The CFTC COT connector needs no key
    - Like every other demo script, if network access isn't available,
      both agents correctly report confidence: 0.0 / risk_level: high
      rather than fabricating a bias
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MIN_DATA_QUALITY, LOG_LEVEL, EIA_API_KEY, FRED_API_KEY
from connectors.cot_connector import CotConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_commodity_fundamentals_officer import (
    ChiefCommodityFundamentalsOfficer, register_commodity_fundamentals_sources,
)
from agents.chief_macro_officer import register_macro_data_sources
from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_strategy_officer import ChiefStrategyOfficer

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def print_report(report):
    print(f"\n=== {report.department}: {report.asset_or_theme} ===")
    print(f"  Bias:        {report.bias.value}  (score: {report.bias_score:+.1f})")
    print(f"  Confidence:  {report.confidence:.1f}/100")
    print(f"  Risk level:  {report.risk_level.value}")
    if report.factor_breakdown:
        print("  Factor breakdown:")
        for f in report.factor_breakdown:
            print(f"    - {f.name}: {f.bias.value} (score {f.score:+.1f}, weight {f.importance_weight}/10)")
    for label, items in (("Evidence", report.evidence), ("Catalysts", report.catalysts), ("Risks", report.risks)):
        if items:
            print(f"  {label}:")
            for item in items:
                print(f"    - {item}")
    if report.data_gaps:
        print("  ⚠ Data gaps:")
        for g in report.data_gaps:
            print(f"    - {g}")


def main():
    manager = DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)

    # NOTE: the exact EIA route/facets are best-effort, not verified live
    # from this environment — see connectors/eia_connector.py's docstring
    # for how to confirm them against EIA's own API browser. The mapping
    # itself lives in one place: agents/chief_commodity_fundamentals_officer.py's
    # EIA_ROUTE_SPECS, shared by this demo, the dashboard, and the daily cycle.
    register_commodity_fundamentals_sources(manager, "Crude Oil", eia_api_key=EIA_API_KEY)
    register_macro_data_sources(manager, fred_api_key=FRED_API_KEY)  # Gold's factors reuse these shared keys
    manager.register("COT_GOLD", primary=CotConnector("GOLD - COMMODITY EXCHANGE INC.", weeks_history=8))
    manager.register(
        "COT_CRUDE_OIL",
        primary=CotConnector("WTI FINANCIAL CRUDE OIL - NEW YORK MERCANTILE EXCHANGE", weeks_history=8),
    )

    print("\n=== AI CFO Platform — Chief Commodity Fundamentals Officer demo (Crude Oil) ===")

    fundamentals_report = ChiefCommodityFundamentalsOfficer(
        manager, commodity="Crude Oil", min_quality=MIN_DATA_QUALITY
    ).analyze("Crude Oil")
    print_report(fundamentals_report)

    cot_report = ChiefCommodityAnalyst(
        manager, cot_key="COT_CRUDE_OIL", min_quality=MIN_DATA_QUALITY
    ).analyze("Crude Oil")
    print_report(cot_report)

    print("\n=== Chief Strategy Officer synthesis (Fundamentals weighted 1.0, COT weighted 0.4) ===")
    synthesis = ChiefStrategyOfficer().synthesize("Crude Oil", [fundamentals_report, cot_report])
    print(f"  Overall Market Score: {synthesis.overall_market_score}/100")
    print(f"  Confidence:           {synthesis.confidence_score}/100")
    print(f"  Bias:                 {synthesis.bias.value} (score {synthesis.bias_score:+.1f})")
    print(f"  Execution Readiness:  {synthesis.execution_readiness}")
    print(f"  Contributing:         {', '.join(synthesis.contributing_departments) or 'none'}")

    print(
        "\n=== Also showing: Gold, now fundamentally backed by US Dollar-related data ===\n"
        "(real yields, Dollar Index, Fed Funds Rate — the same reasoning as USD itself, "
        "since Gold is priced in dollars; see docs/ARCHITECTURE_INSTITUTIONAL_MARKET_REGIME.md)"
    )
    gold_fundamentals = ChiefCommodityFundamentalsOfficer(
        manager, commodity="Gold", min_quality=MIN_DATA_QUALITY
    ).analyze("Gold")
    print_report(gold_fundamentals)

    gold_cot = ChiefCommodityAnalyst(manager, cot_key="COT_GOLD", min_quality=MIN_DATA_QUALITY).analyze("Gold")
    print_report(gold_cot)

    print("\n=== Chief Strategy Officer synthesis for Gold (Fundamentals weighted 1.0, COT weighted 0.4) ===")
    gold_synthesis = ChiefStrategyOfficer().synthesize("Gold", [gold_fundamentals, gold_cot])
    print(f"  Overall Market Score: {gold_synthesis.overall_market_score}/100")
    print(f"  Confidence:           {gold_synthesis.confidence_score}/100")
    print(f"  Bias:                 {gold_synthesis.bias.value} (score {gold_synthesis.bias_score:+.1f})")
    print(f"  Execution Readiness:  {gold_synthesis.execution_readiness}")
    print(f"  Contributing:         {', '.join(gold_synthesis.contributing_departments) or 'none'}")


if __name__ == "__main__":
    main()
