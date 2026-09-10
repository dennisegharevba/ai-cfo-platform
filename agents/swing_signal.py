"""
Swing Signal — a swing-trading-oriented reading of COT positioning
reversals, cross-checked against the platform's broad market news
sentiment.

WHY THIS EXISTS: every other COT-driven read on this platform (Chief
Commodity Analyst / Chief FX Analyst, via agents/positioning_agent_base.py)
is built for a POSITION trader. Its whole scoring model treats the
established multi-week Non-Commercial trend as the thesis, and treats a
weekly move AGAINST that trend (agents.speculative_positioning_analysis's
"reversal_watch" classification) as a RISK to that thesis — something that
REDUCES confidence in staying with the existing position
(MOMENTUM_REVERSAL_PENALTY = -15.0 in positioning_agent_base.py).

A swing trader wants the opposite framing: the moment positioning starts
turning against the established trend IS the setup, not a risk to some
other setup. This module doesn't touch positioning_agent_base.py's scoring
at all (position-trading callers are completely unaffected) — it's a
second, independent read of the exact same COT history, reusing the exact
same underlying classification functions (nothing is duplicated or
re-implemented), for a swing-trading-specific question: "is a reversal
happening right now, and does the broad market news environment back it up
or contradict it?"

Deliberately narrow in scope, matching this platform's "honest scope, not
a fabricated wider read" convention used throughout: this cross-checks
each swing setup against the platform's single BROAD market news read
(agents.chief_sentiment_officer / agents.sentiment_scoring), not
asset-specific news — this platform has no per-commodity or per-currency
news source, only one generic market-news RSS feed. A signal's
`news_alignment` therefore answers "does the general market mood support
this turn," not "is there asset-specific news explaining it." Presenting
it as anything more specific would be a fabricated read this platform
doesn't actually have.

See docs/ARCHITECTURE_SWING_SIGNAL.md for the full account, including why
an extreme positioning percentile is scored as a CONFIDENCE BONUS here
(the opposite sign from positioning_agent_base.py's EXTREME_PERCENTILE_PENALTY)
— a reversal off an already-crowded/extreme reading is a textbook
mean-reversion swing setup, not a risk to be discounted.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .release_schedule import is_new_cot_release_available
from models.swing_signal import (
    SwingSignal,
    SwingDirection,
    NewsAlignment,
    SWING_DIRECTION_LABELS,
    NEWS_ALIGNMENT_LABELS,
)

from .positioning_scoring import net_position_trend_score
from .speculative_positioning_analysis import (
    net_positions_series,
    latest_weekly_change,
    percentile_rank,
    classify_extreme_percentile,
    classify_momentum_signal,
)

SWING_DEPARTMENT = "Swing Signal"

# --- Confidence model ---
# Deliberately simple/small, matching this platform's convention for a
# supporting-signal confidence model (see chief_sentiment_officer.py's
# NEWS_CONFIDENCE=55.0, positioning_agent_base.py's BASE_CONFIDENCE=55.0):
# a swing signal is a fast, narrow, two-input read, not a full multi-
# department synthesis — its confidence should read that way.
BASE_CONFIDENCE = 50.0
NEWS_CONFIRMS_BONUS = 20.0
NEWS_CONTRADICTS_PENALTY = -20.0
# Positive here, unlike positioning_agent_base.py's EXTREME_PERCENTILE_PENALTY
# — see module docstring for why: for a swing setup, a reversal off an
# already-stretched reading is the stronger case, not the weaker one.
EXTREME_PERCENTILE_BONUS = 10.0

# A market-sentiment score (agents.sentiment_scoring.news_sentiment_score,
# -100..+100) is only treated as taking a side once it clears this
# magnitude — the same 10-point cutoff chief_sentiment_officer.py's own
# evidence text already uses for "bullish"/"bearish" vs. "mixed/neutral".
NEWS_NEUTRAL_BAND = 10.0


def _direction_from_weekly_change(weekly_change: float) -> SwingDirection:
    return SwingDirection.BULLISH_TURN if weekly_change > 0 else SwingDirection.BEARISH_TURN


def _news_alignment(direction: SwingDirection, news_score: Optional[float]) -> NewsAlignment:
    if news_score is None:
        return NewsAlignment.NO_DATA
    if abs(news_score) < NEWS_NEUTRAL_BAND:
        return NewsAlignment.NEUTRAL
    news_is_bullish = news_score > 0
    turn_is_bullish = direction == SwingDirection.BULLISH_TURN
    return NewsAlignment.CONFIRMS if news_is_bullish == turn_is_bullish else NewsAlignment.CONTRADICTS


def build_swing_signal(
    asset_or_theme: str,
    cot_history: List[dict],
    news_sentiment_score_value: Optional[float] = None,
    long_key: str = "noncomm_long",
    short_key: str = "noncomm_short",
) -> Optional[SwingSignal]:
    """
    Returns a SwingSignal ONLY when this week's Non-Commercial positioning
    move is a genuine reversal against the broader multi-week trend (see
    agents.speculative_positioning_analysis.classify_momentum_signal's
    "reversal_watch") — exactly the moment a position-trading read treats
    as a risk to the standing thesis, a swing-trading read treats as the
    entry signal itself. Returns None on "continuation" / "stable" /
    "insufficient_data" — there is no swing setup to report this cycle.

    cot_history: newest-first COT history, same shape
    connectors.cot_connector.CotConnector returns (a list of weekly dicts
    with noncomm_long/noncomm_short string fields) — the same raw history
    agents.positioning_agent_base.PositioningAgent already reads for this
    market, so this can be built from the same cached
    core.DataIntegrityManager entry with no extra fetch.

    news_sentiment_score_value: the platform's broad market news sentiment
    score (agents.sentiment_scoring.news_sentiment_score's output, -100..
    +100), or None if unavailable this cycle. See module docstring for why
    this is deliberately broad-market, not asset-specific.
    """
    trend_score = net_position_trend_score(cot_history, long_key, short_key)
    weekly_change = latest_weekly_change(cot_history, long_key, short_key)
    nets = net_positions_series(cot_history, long_key, short_key)
    current_net = nets[0] if nets else None
    pct = percentile_rank(cot_history, long_key, short_key)
    extreme_label = classify_extreme_percentile(pct)
    momentum_signal = classify_momentum_signal(trend_score, weekly_change, current_net)

    if momentum_signal != "reversal_watch":
        return None

    direction = _direction_from_weekly_change(weekly_change)
    alignment = _news_alignment(direction, news_sentiment_score_value)

    confidence = BASE_CONFIDENCE
    if alignment == NewsAlignment.CONFIRMS:
        confidence += NEWS_CONFIRMS_BONUS
    elif alignment == NewsAlignment.CONTRADICTS:
        confidence += NEWS_CONTRADICTS_PENALTY
    if extreme_label is not None:
        confidence += EXTREME_PERCENTILE_BONUS
    confidence = max(0.0, min(100.0, confidence))

    trend_direction = "bullish" if trend_score > 0 else "bearish" if trend_score < 0 else "flat"
    evidence = [
        f"Non-Commercial (large speculator) net position moved {weekly_change:+,.0f} contracts this week, "
        f"against the broader {trend_direction} multi-week trend (trend score {trend_score:+.1f}) — a "
        f"{SWING_DIRECTION_LABELS[direction]} developing.",
    ]
    if pct is not None:
        extreme_text = f" ({extreme_label.replace('_', ' ')})" if extreme_label else ""
        evidence.append(
            f"Current positioning is at the {pct:.0f}th percentile of the fetched history window{extreme_text}."
        )
    if news_sentiment_score_value is not None:
        evidence.append(
            f"Broad market news sentiment score is {news_sentiment_score_value:+.1f} — this "
            f"{NEWS_ALIGNMENT_LABELS[alignment]} the turn."
        )
    else:
        evidence.append("No broad market news sentiment reading was available this cycle.")

    return SwingSignal(
        asset_or_theme=asset_or_theme,
        direction=direction,
        weekly_change=weekly_change,
        trend_score=trend_score,
        percentile=pct,
        extreme_label=extreme_label,
        news_sentiment_score=news_sentiment_score_value,
        news_alignment=alignment,
        confidence=round(confidence, 1),
        evidence=evidence,
    )


def should_send_swing_alert(last_alerted_swing_signal: Optional[dict], now: datetime) -> bool:
    """
    Speed matters for a swing signal (see module docstring — the whole
    point is catching the turn as it happens), but the underlying COT data
    itself only updates once a week. Without a dedupe rule, the exact same
    reversal_watch condition would re-fire a fresh Telegram alert on every
    single weekday the scheduled cycle runs (config/refresh_intervals.py /
    .github/workflows/scheduled_run.yml run Mon-Fri) until the position
    finally turns back — that's spam, not a signal.

    Reuses agents.release_schedule.is_new_cot_release_available rather
    than inventing a separate cooldown timer: alert again only once a real
    new CFTC COT release has happened since the last time THIS asset+
    direction was alerted — the same real-world cadence the underlying
    data actually changes on.

    last_alerted_swing_signal: the dict returned by
    database.report_store.ReportStore.get_latest_alerted_swing_signal()
    for this asset+direction, or None if it's never been alerted before
    (in which case this always returns True — nothing to dedupe against).
    """
    if last_alerted_swing_signal is None:
        return True
    last_alerted_at = datetime.fromisoformat(last_alerted_swing_signal["recorded_at"])
    return is_new_cot_release_available(last_alerted_at, now)
