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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    FRED_API_KEY, SEC_USER_AGENT, NEWS_RSS_URL, MIN_DATA_QUALITY, EIA_API_KEY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_LEVEL,
)
from config.watchlist import WATCHLIST_DAILY, WATCHLIST_WEEKLY

from connectors.fred_connector import FredConnector
from connectors.cot_connector import CotConnector
from connectors.sec_edgar_connector import SecEdgarConnector, REVENUE_FALLBACK_CONCEPTS
from connectors.sec_ticker_lookup import resolve_cik
from connectors.binance_connector import BinanceFuturesConnector
from connectors.news_connector import NewsRssConnector
from connectors.yahoo_history_connector import YahooHistoryConnector

from core.refresh_manager import DataIntegrityManager
from agents.chief_macro_officer import ChiefMacroOfficer, register_macro_data_sources
from agents.chief_bond_strategist import ChiefBondStrategist, KEY_DGS10, KEY_DGS2
from agents.chief_commodity_analyst import ChiefCommodityAnalyst
from agents.chief_commodity_fundamentals_officer import (
    ChiefCommodityFundamentalsOfficer, register_commodity_fundamentals_sources,
)
from agents.chief_fx_analyst import ChiefFXAnalyst
from agents.chief_equity_analyst import ChiefEquityAnalyst
from agents.chief_cryptocurrency_analyst import ChiefCryptocurrencyAnalyst
from agents.chief_sentiment_officer import ChiefSentimentOfficer
from agents.chief_seasonality_officer import ChiefSeasonalityOfficer
from agents.chief_risk_fundamentals_officer import ChiefRiskFundamentalsOfficer
from agents.chief_strategy_officer import ChiefStrategyOfficer
from agents.market_breadth import compute_breadth
from agents.cycle_health import assess_cycle_health
from agents.chief_learning_officer import ChiefLearningOfficer
from agents.chief_execution_officer import ChiefExecutionOfficer
from agents.swing_signal import build_swing_signal, should_send_swing_alert
from database.report_store import ReportStore
from telegram.telegram_alerter import TelegramAlerter, TelegramError

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
    register_macro_data_sources(manager, fred_api_key=FRED_API_KEY)  # all 16 Macro factors
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


def _run_commodity_fundamentals(manager: DataIntegrityManager, asset: str, params: dict):
    """
    asset is treated as the commodity's display name (e.g. "Crude Oil"),
    matched against agents.chief_commodity_fundamentals_officer.COMMODITY_FACTOR_SPECS.
    Commodities with no configured factors (most of them — see that
    module's docstring) get a no-op registration and an honest
    zero-confidence report, not a crash or a fabricated reading.

    Precious metals (Gold, Silver, Platinum, Palladium) need Chief Macro
    Officer's shared Real Yield/Dollar Index/Fed Funds Rate keys populated
    too (their factors reuse those exact keys rather than fetching the
    same FRED series again — see chief_commodity_fundamentals_officer.py's
    override_key mechanism). register_macro_data_sources() is idempotent
    (skips keys already registered), so calling it here is safe and
    correct regardless of whether the "US Macro Outlook" watchlist entry
    already ran earlier in the same cycle — without this call, precious
    metals would always show zero confidence in the real scheduled cycle
    even though the scoring logic itself is fully capable of using the data.
    """
    register_commodity_fundamentals_sources(manager, asset, eia_api_key=EIA_API_KEY)
    register_macro_data_sources(manager, fred_api_key=FRED_API_KEY)
    return ChiefCommodityFundamentalsOfficer(manager, commodity=asset, min_quality=MIN_DATA_QUALITY).analyze(asset)


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
            manager.register(rev_key, primary=SecEdgarConnector(
                cik=cik, concept="Revenues", user_agent=SEC_USER_AGENT, fallback_concepts=REVENUE_FALLBACK_CONCEPTS,
            ))

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


def _run_seasonality(manager: DataIntegrityManager, asset: str, params: dict):
    """
    No data fetch at all — ChiefSeasonalityOfficer is a pure calendar
    lookup (see its own docstring for why it's architecturally NOT a
    BaseAgent). `manager` is accepted only for interface consistency with
    every other runner in DEPARTMENT_RUNNERS; it's unused here.
    """
    return ChiefSeasonalityOfficer().analyze(asset)


def _run_risk_fundamentals(manager: DataIntegrityManager, asset: str, params: dict):
    """
    params must include "ticker" — the Yahoo Finance ticker for this asset
    (e.g. "GC=F" for gold futures, "AAPL" for Apple). Reuses the same
    PRICE_HISTORY_<TICKER> key convention the portfolio-level Chief Risk
    Officer already uses, so a shared fetch serves both if both are ever
    run for the same ticker in the same cycle.
    """
    ticker = params["ticker"]
    key = f"PRICE_HISTORY_{ticker}"
    if not manager.is_registered(key):
        manager.register(key, primary=YahooHistoryConnector(ticker, period="6mo", interval="1d"))
    return ChiefRiskFundamentalsOfficer(manager, ticker=ticker, min_quality=MIN_DATA_QUALITY).analyze(asset)


DEPARTMENT_RUNNERS = {
    "macro": _run_macro,
    "bond": _run_bond,
    "commodity": _run_commodity,
    "commodity_fundamentals": _run_commodity_fundamentals,
    "fx": _run_fx,
    "equity": _run_equity,
    "crypto": _run_crypto,
    "sentiment": _run_sentiment,
    "seasonality": _run_seasonality,
    "risk_fundamentals": _run_risk_fundamentals,
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

    # Department keys whose reports make a "how risky" claim rather than a
    # "which direction" claim — routed through ChiefStrategyOfficer's
    # risk_reports parameter (excluded from bias weighting, but their
    # risk_level/risks/catalysts still feed into the final synthesis).
    # See agents/chief_strategy_officer.py's synthesize() docstring.
    RISK_DEPARTMENT_KEYS = {"risk_fundamentals"}

    # Swing Signal (see agents/swing_signal.py): a second, independent,
    # swing-trading-specific read of the exact same COT data this cycle
    # already fetches for "commodity"/"fx" departments, cross-checked
    # against this cycle's own broad market news sentiment score.
    # Collected opportunistically as the main loop below runs — no extra
    # fetches, no extra network calls. The actual scan happens AFTER the
    # main loop (via _scan_for_swing_signals) so every commodity/FX
    # entry's COT data AND the "sentiment" department's read are both
    # already in hand, regardless of where each falls in the watchlist.
    market_sentiment_score: Optional[float] = None
    cot_entries: List[Tuple[str, str]] = []  # (asset_or_theme, cot_key) pairs, successfully processed this cycle

    for entry in watchlist:
        asset = entry["asset_or_theme"]
        try:
            reports = []
            risk_reports = []
            for dept_key, params in entry.get("departments", {}).items():
                runner = DEPARTMENT_RUNNERS.get(dept_key)
                if runner is None:
                    logger.warning("Unknown department key '%s' for asset '%s' — skipping", dept_key, asset)
                    continue
                report = runner(manager, asset, params)
                learning_officer.record_agent_report(report)
                if dept_key in RISK_DEPARTMENT_KEYS:
                    risk_reports.append(report)
                else:
                    reports.append(report)

                if dept_key == "sentiment":
                    market_sentiment_score = report.bias_score
                elif dept_key in ("commodity", "fx") and "cot_market" in params:
                    cot_entries.append((asset, f"COT_{params['cot_market']}"))

            strategy_report = strategy_officer.synthesize(asset, reports, risk_reports=risk_reports)
            learning_officer.record_strategy_report(strategy_report)

            decision = execution_officer.process(strategy_report)

            results.append({
                "asset": asset,
                "department_count": len(reports) + len(risk_reports),
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

    _scan_for_swing_signals(manager, learning_officer, execution_officer, cot_entries, market_sentiment_score)

    return results


def _scan_for_swing_signals(
    manager: DataIntegrityManager,
    learning_officer: ChiefLearningOfficer,
    execution_officer: ChiefExecutionOfficer,
    cot_entries: List[Tuple[str, str]],
    market_sentiment_score: Optional[float],
) -> None:
    """
    Runs agents.swing_signal.build_swing_signal over every "commodity"/"fx"
    entry this cycle already fetched COT data for — reading it back from
    the manager's own cache (manager.get() on an already-registered,
    unexpired key returns the cached Dataset, no new fetch) rather than
    fetching anything a second time.

    Every detected signal is persisted (so the dashboard's Swing Signals
    page can show it without a live re-scan). Reuses the SAME
    ChiefExecutionOfficer instance's alerter for Telegram delivery — one
    bot, two alert paths — gated by agents.swing_signal.should_send_swing_alert
    rather than execution_officer's own (much stricter, position-trading-
    oriented) evaluate() gate: see agents/swing_signal.py's module
    docstring for why a swing signal is deliberately faster/looser to fire
    than the Chief Execution Officer's confidence/risk/coverage gate. One
    entry's failure (e.g. a genuinely unusable/expired dataset) is logged
    and skipped, never aborts the rest of the scan — the same "never let
    one problem take down the whole system" principle used throughout
    this cycle.
    """
    now = datetime.now(timezone.utc)
    for asset, cot_key in cot_entries:
        try:
            dataset = manager.get(cot_key)
            if not dataset.is_usable():
                continue
            history = dataset.payload.get("history", [])
            signal = build_swing_signal(asset, history, market_sentiment_score)
            if signal is None:
                continue

            last_alerted = learning_officer.store.get_latest_alerted_swing_signal(asset, signal.direction.value)
            alert_sent = False
            if should_send_swing_alert(last_alerted, now) and execution_officer.alerter is not None:
                try:
                    execution_officer.alerter.send_message(signal.headline())
                    alert_sent = True
                except TelegramError as exc:
                    logger.error("Swing alert failed to send for '%s': %s", asset, exc)

            learning_officer.store.save_swing_signal(signal, alert_sent=alert_sent)
            logger.info(
                "Swing signal: %s %s (confidence %.0f)%s",
                asset, signal.direction.value, signal.confidence, " [ALERTED]" if alert_sent else "",
            )
        except Exception as exc:  # noqa: BLE001 — deliberate: isolate one asset's failure from the rest
            logger.error("Swing signal scan failed for '%s': %s", asset, exc, exc_info=True)


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

    # Created explicitly (rather than letting run_cycle() build its own)
    # so it can be reused afterward for Market Breadth — see below. Every
    # equity's "risk_fundamentals" department already populates a
    # PRICE_HISTORY_<TICKER> dataset in this exact manager; Market Breadth
    # reuses those same cached datasets rather than fetching anything new.
    manager = DataIntegrityManager(min_quality_threshold=MIN_DATA_QUALITY)
    # Also created explicitly (rather than letting run_cycle() build its
    # own) so its store can be queried afterward for this cycle's Swing
    # Signals — see _print_swing_signals() below.
    cycle_started_at = datetime.now(timezone.utc).isoformat()
    learning_officer = ChiefLearningOfficer(store=ReportStore("ai_cfo_platform.db"))
    results = run_cycle(watchlist, manager=manager, learning_officer=learning_officer)

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

    health = assess_cycle_health(results)
    if health.is_systemic_issue:
        print(f"\n⚠️  SYSTEMIC ISSUE LIKELY ({health.healthy_count}/{health.total_entries} entries healthy):")
        for reason in health.reasons:
            print(f"   - {reason}")
        logger.warning("Cycle health check flagged a likely systemic issue: %s", "; ".join(health.reasons))
    else:
        logger.info(
            "Cycle health: %d/%d healthy, %d degraded, %d errored — no systemic pattern detected",
            health.healthy_count, health.total_entries, health.degraded_count, health.error_count,
        )

    if args.watchlist == "daily":
        _print_swing_signals(learning_officer, since=cycle_started_at)

    if args.watchlist == "weekly":
        _print_market_breadth(manager)


def _print_swing_signals(learning_officer: ChiefLearningOfficer, since: str) -> None:
    """Summarizes every Swing Signal (see agents/swing_signal.py) detected
    THIS cycle — since=cycle_started_at, not "recent" in general, so a
    quiet cycle honestly prints nothing rather than stale signals from a
    prior run."""
    signals = learning_officer.store.get_swing_signals(since=since, limit=200)
    if not signals:
        return
    print(f"\n=== Swing Signals ({len(signals)} detected this cycle) ===")
    for s in signals:
        emoji = "🔻" if s["direction"] == "bearish_turn" else "🔺"
        alert_marker = " [ALERTED]" if s["alert_sent"] else ""
        print(
            f"  {emoji} {s['asset_or_theme']}: {s['direction']} — news {s['news_alignment']}, "
            f"confidence {s['confidence']:.0f}{alert_marker}"
        )


def _print_market_breadth(manager: DataIntegrityManager) -> None:
    """
    Market Breadth (per docs/ARCHITECTURE_POSITIONING_SEPARATION.md) is
    computed entirely from the PRICE_HISTORY_<TICKER> datasets the weekly
    cycle's "risk_fundamentals" department already populated for every
    equity — zero additional fetches. Only run after the WEEKLY cycle,
    since that's the one that actually populates a large-cap universe's
    worth of price history; the daily cycle only covers a handful of
    tickers (commodities, S&P500/NASDAQ100 index proxies), too small a
    sample for a meaningful breadth read.
    """
    price_histories = {}
    for key in list(manager._registrations.keys()):
        if not key.startswith("PRICE_HISTORY_"):
            continue
        try:
            dataset = manager.get(key)
        except Exception:
            price_histories[key] = []
            continue
        # Every registered key counts toward universe_size regardless of
        # usability — an empty list here still registers the ticker as
        # "requested," so compute_breadth's own usable_count correctly
        # shows how many actually succeeded (e.g. "0 of 5 usable" is an
        # honest signal that 5 were attempted and all failed, not the
        # misleading "0 of 0" that pre-filtering to only-usable datasets
        # before this point would have produced).
        price_histories[key] = dataset.payload.get("history", []) if dataset.is_usable() else []

    breadth = compute_breadth(price_histories)
    print(f"\n=== Market Breadth ({breadth.usable_count} of {breadth.universe_size} large-cap tickers usable) ===")
    print(f"  Advance/Decline: {breadth.advancers} up / {breadth.decliners} down / {breadth.unchanged} unchanged")
    if breadth.pct_above_50dma is not None:
        print(f"  % above 50-day SMA: {breadth.pct_above_50dma:.1f}% (of {breadth.sma_computable_count} computable)")
    print(f"  New highs / lows (within the {breadth.window_days}-day fetched window): {breadth.new_highs} / {breadth.new_lows}")


if __name__ == "__main__":
    main()
