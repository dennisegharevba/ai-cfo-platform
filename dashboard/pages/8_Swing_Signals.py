"""
Swing Signals page — the swing-trading-specific view of COT positioning
reversals (see agents/swing_signal.py), cross-checked against the
platform's broad market news sentiment.

Deliberately separate from the Alerts & Execution page (page 6): that
page gates on the Chief Execution Officer's position-trading thresholds
(confidence >= 65, low/moderate risk, broad multi-department coverage) —
built for someone sizing a position to hold for weeks/months. This page
shows something narrower and deliberately faster to trigger: the moment
Non-Commercial (large speculator) positioning starts turning AGAINST the
established multi-week trend — the same moment the position-trading
departments discount as a risk to their standing thesis, this page treats
as the entry setup itself. The two pipelines are fully independent and
read the same underlying COT data; either can be checked for the same
market without affecting the other. See docs/ARCHITECTURE_SWING_SIGNAL.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.dashboard_utils import get_manager, inject_terminal_css, get_report_store
from config.settings import (
    NEWS_RSS_URL, MIN_DATA_QUALITY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SWING_SIGNAL_ALERTS_ENABLED,
)
from config.watchlist import WATCHLIST_DAILY

from connectors.cot_connector import CotConnector
from connectors.news_connector import NewsRssConnector

from agents.chief_sentiment_officer import ChiefSentimentOfficer
from agents.swing_signal import build_swing_signal
from telegram.telegram_alerter import TelegramAlerter, TelegramError

st.set_page_config(page_title="Swing Signals — AI CFO Platform", page_icon="🌀", layout="wide")
inject_terminal_css()
st.title("🌀 Swing Signals")
st.caption(
    "COT positioning reversals, read for a swing trader rather than a position trader — the moment "
    "Non-Commercial (large speculator) positioning starts turning against the established multi-week "
    "trend, cross-checked against broad market news sentiment. See docs/ARCHITECTURE_SWING_SIGNAL.md "
    "for the full reasoning, including the one honest limitation: news is broad-market, not per-asset "
    "(this platform has no per-commodity/per-currency news source)."
)

if not SWING_SIGNAL_ALERTS_ENABLED:
    st.warning(
        "Telegram alerts are currently disabled for this feature. A real backtest across three "
        "independent assets (Gold, EUR/USD, WTI Crude Oil) found a consistent NEGATIVE correlation "
        "with forward returns and a losing simulated strategy (profit factor under 1.0) on all three "
        "— see docs/ARCHITECTURE_SWING_SIGNAL.md's \"Backtesting\" section. Signals below are still "
        "detected and saved normally; only the Telegram send is gated. Set "
        "SWING_SIGNAL_ALERTS_ENABLED=true once this is resolved."
    )

store = get_report_store()

_COT_MARKETS = [
    (entry["asset_or_theme"], params["cot_market"])
    for entry in WATCHLIST_DAILY
    for dept, params in entry.get("departments", {}).items()
    if dept in ("commodity", "fx")
]

st.caption(f"Watching {len(_COT_MARKETS)} FX/commodity markets from your configured watchlist (config/watchlist.py).")

if st.button("🔄 Run live scan now", type="primary"):
    manager = get_manager()
    progress = st.progress(0.0, text="Fetching broad market news sentiment...")

    # One shared broad-market news read for every market this scan checks
    # — see the module docstring above and agents/swing_signal.py for why
    # this is deliberately broad-market rather than a fabricated per-asset read.
    news_key = "MARKET_NEWS"
    if not manager.is_registered(news_key):
        manager.register(news_key, primary=NewsRssConnector(NEWS_RSS_URL))
    sentiment_report = ChiefSentimentOfficer(manager, news_key=news_key, min_quality=MIN_DATA_QUALITY).analyze(
        "Broad Market Sentiment"
    )
    market_sentiment_score = sentiment_report.bias_score if sentiment_report.confidence > 0 else None

    detected = []
    failures = []
    for i, (asset, cot_market) in enumerate(_COT_MARKETS):
        progress.progress(i / max(len(_COT_MARKETS), 1), text=f"Scanning {asset}...")
        key = f"COT_{cot_market}"
        try:
            if not manager.is_registered(key):
                manager.register(key, primary=CotConnector(cot_market, weeks_history=8))
            dataset = manager.get(key)
            if dataset.is_usable():
                history = dataset.payload.get("history", [])
                signal = build_swing_signal(asset, history, market_sentiment_score)
                if signal is not None:
                    store.save_swing_signal(signal)
                    detected.append(signal)
        except Exception as exc:  # noqa: BLE001 — one market's failure shouldn't block the rest of the scan
            failures.append(f"{asset}: {exc}")

    progress.empty()
    if detected:
        st.success(f"Found {len(detected)} swing signal(s) this scan.")
    else:
        st.info("No COT reversals detected against any market's trend this scan.")
    if failures:
        with st.expander(f"{len(failures)} market(s) failed to fetch"):
            for f in failures:
                st.markdown(f"- {f}")
    st.rerun()

st.divider()
st.subheader("Recent signals")

lookback_days = st.slider("Show signals from the last N days", 1, 30, 7)
since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
signals = store.get_swing_signals(since=since, limit=200)

if not signals:
    st.info(
        "No swing signals in this window yet. Run a live scan above, or wait for the scheduled "
        "research cycle (scripts/run_daily_cycle.py, via .github/workflows/scheduled_run.yml) to "
        "detect one automatically."
    )
else:
    has_creds = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    for s in signals:
        emoji = "🔻" if s["direction"] == "bearish_turn" else "🔺"
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 2])
            col1.markdown(f"### {emoji} {s['asset_or_theme']}")
            col2.metric("Confidence", f"{s['confidence']:.0f}/100")
            news_label = s["news_alignment"].replace("_", " ").title()
            col3.markdown(f"**Broad market news**\n\n{news_label}")

            for e in s["evidence"]:
                st.markdown(f"- {e}")

            caption = f"Detected {s['recorded_at']}"
            if s["alert_sent"]:
                caption += " · ✅ Telegram alert sent"
            st.caption(caption)

            if not s["alert_sent"] and has_creds:
                if not SWING_SIGNAL_ALERTS_ENABLED:
                    st.caption(
                        "Telegram alert disabled pending the backtest resolution above "
                        "(set SWING_SIGNAL_ALERTS_ENABLED=true to re-enable)."
                    )
                elif st.button("Send Telegram alert for this signal", key=f"send_swing_{s['id']}"):
                    alerter = TelegramAlerter(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
                    headline = (
                        f"{emoji} {s['asset_or_theme']}: COT positioning is turning "
                        f"{'BEARISH' if s['direction'] == 'bearish_turn' else 'BULLISH'} against the "
                        f"established trend — broad market news {news_label.lower()} it "
                        f"(confidence {s['confidence']:.0f}/100)"
                    )
                    try:
                        alerter.send_message(headline)
                        store.mark_swing_signal_alerted(s["id"])
                        st.success("Alert sent.")
                        st.rerun()
                    except TelegramError as exc:
                        st.error(f"Send failed: {exc}")
