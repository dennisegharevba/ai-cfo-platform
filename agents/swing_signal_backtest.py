"""
Swing Signal backtesting — closes the gap agents/backtest_signals.py's own
docstring flagged as deliberately deferred: "COT-based Commodity/FX
Analyst — would need extending connectors/cot_connector.py to fetch a
wide historical date range (CFTC's API supports this, but it's unbuilt)."
That extension now exists (connectors.cot_connector.fetch_cot_history_range)
— this module is what uses it, specifically for agents/swing_signal.py.

WHY A SEPARATE MODULE, NOT A FUNCTION ADDED TO backtest_signals.py:
every signal in that file is tested on a REGULAR calendar grid (one score
per --step-days, e.g. every 30 days), because those signals (Seasonality,
VIX, Macro factors) have a value on essentially any date. Swing Signal is
architecturally different — agents.swing_signal.build_swing_signal()
returns None on most weeks BY DESIGN (a signal only exists on a genuine
reversal_watch). Testing it on a fixed calendar grid would mostly ask
"was there a signal on this arbitrary date" and get None almost every
time, wasting most of the sample. The honest way to backtest an EVENT
signal is to walk the full weekly COT history sequentially and record a
score only on the weeks it actually fired — exactly what
swing_signal_history() below does. Its output shape
(List[Tuple[date, float]]) is identical to every other signal's, so it
plugs into agents.backtest_engine.run_backtest() (correlation) and
agents.strategy_backtest.simulate_strategy() (simulated trades: win rate,
Sharpe, profit factor) completely unmodified — see
scripts/run_swing_signal_backtest.py for both wired up together.

HONEST LIMITATION, same one build_swing_signal() itself already carries:
no historical news sentiment is used here — agents/backtest_signals.py's
own docstring: "News Sentiment — genuinely impossible with this
platform's RSS-based connector, which has no historical headline
archive. Permanently excluded, not just deferred." Every backtested
signal here is therefore scored as if news_alignment were always NO_DATA
(BASE_CONFIDENCE, no news bonus/penalty — see agents/swing_signal.py).
This means the backtest answers a genuinely narrower question than the
live feature: "does the COT-reversal-off-an-extreme-reading mechanism
ALONE have predictive value?" — not "does COT + news." If the COT-only
mechanism doesn't hold up here, the news cross-check can't be assumed to
be what rescues it live either, since news was never validated at all.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from .swing_signal import build_swing_signal
from models.swing_signal import SwingDirection
from connectors.cot_connector import fetch_cot_history_range


def _parse_report_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def swing_signal_history(
    asset_or_theme: str,
    market_and_exchange_name: str,
    start_date: date,
    end_date: date,
    window_weeks: int = 8,
) -> List[Tuple[date, float]]:
    """
    Walks the full CFTC COT history for `market_and_exchange_name` between
    start_date and end_date, and returns one (report_date, signed_confidence)
    pair for every week agents.swing_signal.build_swing_signal() would have
    fired a signal. signed_confidence is +confidence for a BULLISH_TURN,
    -confidence for a BEARISH_TURN — matching the sign convention every
    other signal in agents/backtest_signals.py already uses (positive =
    bullish reading), so it plugs into the same downstream engines
    unmodified. Weeks with no signal (continuation / stable /
    insufficient_data) are simply OMITTED, not scored as zero — an event
    signal's absence isn't itself a reading to correlate against returns
    the way a continuous signal's neutral value would be.

    window_weeks: how many trailing weekly reports build_swing_signal()
    sees at each point. Defaults to 8, matching what the live path fetches
    (connectors.cot_connector.CotConnector's default weeks_history, used
    by both dashboard/pages/8_Swing_Signals.py and
    scripts/run_daily_cycle.py) — kept in sync deliberately so a backtest
    result reflects what the live feature actually sees, not a wider or
    narrower window that would quietly answer a different question.

    Fetches from start_date minus a buffer so the FIRST testable week
    still has a full window_weeks of prior history behind it — otherwise
    the first ~window_weeks of the requested start_date..end_date range
    would be silently untestable, shrinking the range without saying so.

    Returns an empty list (never raises) if the underlying COT fetch
    fails — the caller (a backtest script) simply reports 0 usable signal
    readings rather than crashing, matching this platform's "never
    fabricate, always degrade with an honest count" convention.
    """
    fetch_start = start_date - timedelta(weeks=window_weeks * 2)  # generous buffer for the leading window

    raw_history = fetch_cot_history_range(market_and_exchange_name, fetch_start, end_date)
    if not raw_history:
        return []

    # raw_history is oldest-first (fetch_cot_history_range's $order ASC).
    # Attach parsed dates once; skip any row whose date won't parse.
    dated_rows: List[Tuple[date, dict]] = []
    for row in raw_history:
        d = _parse_report_date(row.get("report_date"))
        if d is not None:
            dated_rows.append((d, row))
    dated_rows.sort(key=lambda pair: pair[0])

    results: List[Tuple[date, float]] = []
    for i in range(window_weeks - 1, len(dated_rows)):
        report_date, _ = dated_rows[i]
        if report_date < start_date or report_date > end_date:
            continue

        # build_swing_signal wants NEWEST-first, matching the live
        # CotConnector.fetch()'s payload["history"] shape exactly.
        window = [row for _, row in dated_rows[i - window_weeks + 1 : i + 1]]
        window_newest_first = list(reversed(window))

        signal = build_swing_signal(asset_or_theme, window_newest_first, news_sentiment_score_value=None)
        if signal is None:
            continue

        signed_confidence = signal.confidence if signal.direction == SwingDirection.BULLISH_TURN else -signal.confidence
        results.append((report_date, signed_confidence))

    return results
