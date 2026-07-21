"""
Automated research cycle — the script GitHub Actions runs on a schedule.
Turns the manual "run a demo script" pattern from Phases 2-9 into
something that can run unattended: for every entry in the selected
watchlist (config/watchlist.py), run the configured departments,
synthesize via the Chief Strategy Officer, persist everything via the
Chief Learning Officer, and alert via the Chief Execution Officer if it
clears the gate.

Two watchlists, two schedules:
    python scripts/run_daily_cycle.py             # WATCHLIST_DAILY (default)
    python scripts/run_daily_cycle.py --watchlist weekly   # WATCHLIST_WEEKLY (equities)

See config/watchlist.py's docstring for why equities are split onto a
separate, less-frequent cadence (fundamentals don't change daily) and
.github/workflows/ for the two corresponding scheduled workflows.

One asset's failure (e.g. a connector unreachable) is isolated and logged
— it does NOT stop the rest of the watchlist from being processed. This is
the same "never let one problem take down the whole system" principle
behind the Data Integrity & Refresh Manager (Phase 1), applied at the
orchestration level: a scheduled run with 350 of 357 assets processed and
7 logged failures is a normal, useful outcome, not something that should
be treated as a CI-red failure.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    FRED_API_KEY, SEC_USER_AGENT, NEWS_RSS_URL, MIN_DATA_QUALITY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_LEVEL,
)
from config.watchlist import WATCHLIST_DAILY, WATCHLIST_WEEKLY

from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.yahoo_history_connector import YahooHistoryConnector
from connectors.sec_edgar_connector import SecEdgarConnector
from connectors.sec_ticker_lookup import resolve_cik
from connectors.binance_connector import BinanceFuturesConnector
from connectors.news_connector import NewsRssConnector

from core.refresh_manager import DataIntegrityManager
from agents.chief_macro_officer import ChiefMacroOfficer, KEY_CPI, KEY_UNRATE
from agents.chief_bond_strategist import ChiefBondStrategist, KEY_DGS10, KEY_DGS2
from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_fx_analyst import ChiefFXAnalyst
from agents.chief_equity_analyst import ChiefEquityAnalyst
from agents.chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from agents.chief_sentiment_officer import ChiefSentimentOfficer
from agents.chief_technical_officer import ChiefTechnicalOfficer
from agents.chief_strategy_officer import ChiefStrategyOfficer
from agents.chief_learning_officer import ChiefLearningOfficer
from agents.chief_execution_officer import ChiefExecutionOfficer
from database.report_store import ReportStore
from telegram.telegram_alerter import TelegramAlerter

logger = logging.getLogger("ai_cfo.daily_cycle")

# Small courtesy delay between per-ticker SEC EDGAR fundamentals calls,
# specifically for the equity department (the only one making a large
# volume of calls to a single free government API in one run — the weekly
# watchlist alone is ~350 tickers x 2 EDGAR calls). This value hasn't been
# tuned against SEC's live servers from this environment; treat it as a
# reasonable starting point, not a guarantee of compliance with any rate
# limit SEC enforces.
SEC_EQUITY_COURTESY_DELAY_SECONDS = 0.2


def _run_macro(manager: DataIntegrityManager, asset: str, params: dict):
    if not manager.is_registered(KEY_CPI):
        manager.register(KEY_CPI, primary=FredConnector(series_id="CPIAUCSL", api_key=FRED_API_KEY))
    if not manager.is_registered(KEY_UNRATE):
        manager.register(KEY_UNRATE, primary=FredConnector(series_id="UNRATE", api_key=FRED_API_KEY))
    return ChiefMacroOfficer(manager, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_bond(manager: DataIntegrityManager, asset: str, params: dict):
    if not manager.is_registered(KEY_DGS10):
        manager.register(KEY_DGS10, primary=FredConnector(series_id="DGS10", api_key=FRED_API_KEY))
    if not manager.is_registered(KEY_DGS2):
        manager.register(KEY_DGS2, primary=FredConnector(series_id="DGS2", api_key=FRED_API_KEY))
    return ChiefBondStrategist(manager, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_commodity(manager: DataIntegrityManager, asset: str, params: dict):
    key = f"COT_{params['cot_market']}"
    if not manager.is_registered(key):
        manager.register(key, primary=CotConnector(params["cot_market"], weeks_history=8))
    return ChiefCommodityAnalyst(manager, cot_key=key, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_fx(manager: DataIntegrityManager, asset: str, params: dict):
    key = f"COT_{params['cot_market']}"
    if not manager.is_registered(key):
        manager.register(key, primary=CotConnector(params["cot_market"], weeks_history=8))
    return ChiefFXAnalyst(manager, cot_key=key, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_equity(manager: DataIntegrityManager, asset: str, params: dict):
    """
    asset is treated as the ticker itself (e.g. "AAPL"). CIK is resolved
    automatically via SEC's free bulk ticker/CIK mapping (one fetch covers
    every ticker in the watchlist — see connectors/sec_ticker_lookup.py)
    rather than requiring a hand-entered "cik" param. If the ticker isn't
    found in that mapping, this returns a zero-confidence report (via
    BaseAgent's normal missing-data path) rather than raising — a bad
    ticker in the watchlist degrades gracefully like any other data gap.
    """
    cik = params.get("cik") or resolve_cik(manager, asset, user_agent=SEC_USER_AGENT)
    eps_key, rev_key = f"SEC_{asset}_EPS", f"SEC_{asset}_REV"

    if cik is not None:
        if not manager.is_registered(eps_key):
            manager.register(eps_key, primary=SecEdgarConnector(cik=cik, concept="EarningsPerShareDiluted", user_agent=SEC_USER_AGENT))
        if not manager.is_registered(rev_key):
            manager.register(rev_key, primary=SecEdgarConnector(cik=cik, concept="Revenues", user_agent=SEC_USER_AGENT))

    time.sleep(SEC_EQUITY_COURTESY_DELAY_SECONDS)
    return ChiefEquityAnalyst(manager, eps_key=eps_key, revenue_key=rev_key, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_crypto(manager: DataIntegrityManager, asset: str, params: dict):
    key = f"CRYPTO_{params['symbol']}"
    if not manager.is_registered(key):
        manager.register(key, primary=BinanceFuturesConnector(params["symbol"], history_limit=30))
    return ChiefCryptocurrencyAnalyst(manager, crypto_key=key, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_sentiment(manager: DataIntegrityManager, asset: str, params: dict):
    key = "MARKET_NEWS"
    if not manager.is_registered(key):
        manager.register(key, primary=NewsRssConnector(NEWS_RSS_URL))
    return ChiefSentimentOfficer(manager, news_key=key, min_quality=MIN_DATA_QUALITY).analyze(asset)


def _run_technical(manager: DataIntegrityManager, asset: str, params: dict):
    key = f"PRICE_HISTORY_{params['ticker']}"
    if not manager.is_registered(key):
        manager.register(key, primary=YahooHistoryConnector(params["ticker"], period="6mo", interval="1d"))
    return ChiefTechnicalOfficer(manager, price_key=key, min_quality=MIN_DATA_QUALITY).analyze(asset)


DEPARTMENT_RUNNERS = {
    "macro": _run_macro,
    "bond": _run_bond,
    "commodity": _run_commodity,
    "fx": _run_fx,
    "equity": _run_equity,
    "crypto": _run_crypto,
    "sentiment": _run_sentiment,
    "technical": _run_technical,
}


def run_cycle(
    watchlist: List[Dict[str, Any]],
    manager: Optional[DataIntegrityManager] = None,
    learning_officer: Optional[ChiefLearningOfficer] = None,
    execution_officer: Optional[ChiefExecutionOfficer] = None,
) -> List[Dict[str, Any]]:
    """
    Run every watchlist entry end-to-end: departments -> synthesis ->
    persistence -> execution gate. Returns a per-asset summary list.

    Each watchlist entry is processed inside its own try/except — a bug or
    an unreachable source for ONE asset is logged and skipped, never
    aborts the rest of the cycle.
    """
    manager = manager or DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)
    learning_officer = learning_officer or ChiefLearningOfficer(store=ReportStore("ai_cfo_platform.db"))
    strategy_officer = ChiefStrategyOfficer()
    execution_officer = execution_officer or ChiefExecutionOfficer(alerter=_build_alerter())

    results: List[Dict[str, Any]] = []

    for entry in watchlist:
        asset = entry["asset_or_theme"]
        try:
            reports = []
            for dept_key, params in entry.get("departments", {}).items():
                runner = DEPARTMENT_RUNNERS.get(dept_key)
                if runner is None:
                    logger.warning("Unknown department key '%s' for asset '%s' — skipping", dept_key, asset)
                    continue
                report = runner(manager, asset, params)
                reports.append(report)
                learning_officer.record_agent_report(report)

            strategy_report = strategy_officer.synthesize(asset, reports)
            learning_officer.record_strategy_report(strategy_report)

            decision = execution_officer.process(strategy_report)

            results.append({
                "asset": asset,
                "department_count": len(reports),
                "bias": strategy_report.bias.value,
                "bias_score": strategy_report.bias_score,
                "confidence_score": strategy_report.confidence_score,
                "risk_level": strategy_report.risk_level.value,
                "alert_should_fire": decision.should_alert,
                "alert_sent": decision.alert_sent,
                "alert_blocking_reasons": decision.blocking_reasons,
                "error": None,
            })
            logger.info(
                "Processed %s: bias=%s score=%.1f confidence=%.1f alert=%s",
                asset, strategy_report.bias.value, strategy_report.bias_score,
                strategy_report.confidence_score, decision.should_alert,
            )

        except Exception as exc:  # noqa: BLE001 — deliberate: isolate one asset's failure from the rest
            logger.error("Failed to process asset '%s': %s", asset, exc, exc_info=True)
            results.append({"asset": asset, "error": str(exc)})

    return results


def _build_alerter() -> Optional[TelegramAlerter]:
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        return TelegramAlerter(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    return None


def main():
    parser = argparse.ArgumentParser(description="Run the AI CFO Platform's automated research cycle.")
    parser.add_argument(
        "--watchlist", choices=["daily", "weekly"], default="daily",
        help="Which watchlist to run: 'daily' (macro/FX/commodities/crypto/sentiment, fast) "
             "or 'weekly' (the full equity universe — slower, and only worth running "
             "as often as fundamentals actually change).",
    )
    args = parser.parse_args()

    watchlist = WATCHLIST_WEEKLY if args.watchlist == "weekly" else WATCHLIST_DAILY

    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting '%s' research cycle over %d watchlist entries", args.watchlist, len(watchlist))

    results = run_cycle(watchlist)

    print(f"\n=== {args.watchlist.title()} Research Cycle Summary ({len(results)} entries) ===")
    for r in results:
        if r.get("error"):
            print(f"  ❌ {r['asset']}: ERROR — {r['error']}")
        else:
            alert_marker = "🚨 ALERT" if r["alert_should_fire"] else "  (no alert)"
            print(
                f"  {alert_marker} {r['asset']}: {r['bias']} (score {r['bias_score']:+.1f}), "
                f"confidence {r['confidence_score']:.0f}, risk {r['risk_level']} "
                f"[{r['department_count']} department(s)]"
            )

    errors = [r for r in results if r.get("error")]
    if errors:
        logger.warning("%d of %d watchlist entries failed this cycle", len(errors), len(results))


if __name__ == "__main__":
    main()
