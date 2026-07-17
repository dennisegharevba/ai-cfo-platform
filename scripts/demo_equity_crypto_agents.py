"""
Phase 4 demo: register real SEC EDGAR fundamentals for Apple Inc. and real
Binance futures data for BTCUSDT, then run the Chief Equity Analyst and
Chief Cryptocurrency Analyst against them.

Run:
    python scripts/demo_equity_crypto_agents.py

Notes:
    - SEC EDGAR requires a real SEC_USER_AGENT in .env (a descriptive string
      with contact info, e.g. "AI CFO Platform you@example.com") — SEC
      commonly rejects requests without one.
    - Binance's public endpoints need no API key.
    - Like the other demo scripts, if network access to data.sec.gov or
      fapi.binance.com isn't available, both agents will correctly report
      confidence: 0.0 / risk_level: high rather than fabricating a bias.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MIN_DATA_QUALITY, LOG_LEVEL, SEC_USER_AGENT
from connectors.sec_edgar_connector import SecEdgarConnector
from connectors.binance_connector import BinanceFuturesConnector
from core.refresh_manager import DataIntegrityManager
from agents.chief_equity_analyst import ChiefEquityAnalyst
from agents.chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst

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

    # Apple Inc. CIK = 320193
    manager.register(
        "AAPL_EPS",
        primary=SecEdgarConnector(cik="320193", concept="EarningsPerShareDiluted", user_agent=SEC_USER_AGENT),
    )
    manager.register(
        "AAPL_REVENUE",
        primary=SecEdgarConnector(cik="320193", concept="Revenues", user_agent=SEC_USER_AGENT),
    )
    manager.register("CRYPTO_BTC", primary=BinanceFuturesConnector("BTCUSDT", history_limit=30))

    print("\n=== AI CFO Platform — Phase 4: Chief Equity Analyst + Chief Cryptocurrency Analyst demo ===")

    equity_report = ChiefEquityAnalyst(
        manager, eps_key="AAPL_EPS", revenue_key="AAPL_REVENUE", min_quality=MIN_DATA_QUALITY
    ).analyze("AAPL")
    print_report(equity_report)

    crypto_report = ChiefCryptocurrencyAnalyst(
        manager, crypto_key="CRYPTO_BTC", min_quality=MIN_DATA_QUALITY
    ).analyze("BTC")
    print_report(crypto_report)

    print("\n=== Data integrity status report ===")
    for entry in manager.status_report():
        print(entry)


if __name__ == "__main__":
    main()
