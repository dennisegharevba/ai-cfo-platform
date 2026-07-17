"""
Phase 1 demo: register a few real, free data sources with the
DataIntegrityManager and show the full fetch -> validate -> score -> gate
pipeline working end-to-end.

Run:
    python scripts/demo_refresh.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import FRED_API_KEY, MIN_DATA_QUALITY, LOG_LEVEL
from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.yahoo_connector import YahooConnector
from core.refresh_manager import DataIntegrityManager

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main():
    manager = DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)

    # Macro: CPI from FRED (requires a free API key in .env)
    manager.register("FRED_CPI", primary=FredConnector(series_id="CPIAUCSL", api_key=FRED_API_KEY))

    # Commodity positioning: Gold COT from CFTC (no key needed)
    manager.register(
        "COT_GOLD",
        primary=CotConnector(market_and_exchange_name="GOLD - COMMODITY EXCHANGE INC."),
    )

    # Equity price: S&P 500 index proxy via Yahoo (no key needed)
    manager.register("PRICE_SPY", primary=YahooConnector(ticker="SPY"))

    print("\n=== AI CFO Platform — Phase 1: Data Integrity & Refresh Manager demo ===\n")

    for key in ("FRED_CPI", "COT_GOLD", "PRICE_SPY"):
        dataset = manager.get(key)
        usable = dataset.is_usable(min_quality=MIN_DATA_QUALITY)
        print(f"--- {key} ---")
        print(f"  source:            {dataset.source}")
        print(f"  validation_status: {dataset.validation_status.value}")
        print(f"  quality_score:     {dataset.quality_score}")
        print(f"  provider_ts:       {dataset.provider_timestamp}")
        print(f"  is_usable():       {usable}")
        if usable:
            print(f"  payload preview:   {str(dataset.payload)[:200]}")
        else:
            print(f"  BLOCKED — notes:   {dataset.notes}")
        print()

    print("=== Refresh audit log ===")
    for entry in manager.refresh_log:
        print(entry)


if __name__ == "__main__":
    main()
