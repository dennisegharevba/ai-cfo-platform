"""
Daily research cycle — the script GitHub Actions runs on a schedule
(.github/workflows/scheduled_run.yml). Turns the manual "run a demo script"
pattern from Phases 2-9 into something that can run unattended: for every
entry in config/watchlist.py, run the configured departments, synthesize
via the Chief Strategy Officer, persist everything via the Chief Learning
Officer, and alert via the Chief Execution Officer if it clears the gate.

Run manually:
    python scripts/run_daily_cycle.py

One asset's failure (e.g. a connector unreachable) is isolated and logged
— it does NOT stop the rest of the watchlist from being processed. This is
the same "never let one problem take down the whole system" principle
behind the Data Integrity & Refresh Manager (Phase 1), applied at the
orchestration level: a scheduled run with 4 of 5 assets processed and 1
logged failure is a normal, useful outcome, not something that should be
treated as a CI-red failure.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    FRED_API_KEY, SEC_USER_AGENT, NEWS_RSS_URL, MIN_DATA_QUALITY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_LEVEL,
)
from config.watchlist import WATCHLIST

from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.yahoo_history_connector import YahooHistoryConnector
from connectors.sec_edgar_connector import SecEdgarConnector
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
    eps_key, rev_key = f"SEC_{asset}_EPS", f"SEC_{asset}_REV"
    if not manager.is_registered(eps_key):
        manager.register(eps_key, primary=SecEdgarConnector(cik=params["cik"], concept="EarningsPerShareDiluted", user_agent=SEC_USER_AGENT))
    if not manager.is_registered(rev_key):
        manager.register(rev_key, primary=SecEdgarConnector(cik=params["cik"], concept="Revenues", user_agent=SEC_USER_AGENT))
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
    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting daily research cycle over %d watchlist entries", len(WATCHLIST))

    results = run_cycle(WATCHLIST)

    print("\n=== Daily Research Cycle Summary ===")
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
