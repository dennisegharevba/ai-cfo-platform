from datetime import datetime, timedelta, timezone

from agents.swing_signal import build_swing_signal, should_send_swing_alert
from models.swing_signal import SwingDirection, NewsAlignment


def _row(long_, short_, date="2026-07-01"):
    return {"noncomm_long": str(long_), "noncomm_short": str(short_), "report_date": date}


# --- build_swing_signal: only fires on a genuine reversal ---

def test_no_signal_on_continuation():
    # oldest -> newest: net building the whole way (13000 -> 40000 -> 55000),
    # weekly move (55000-40000=15000) AGREES with the broader trend -> continuation, not a swing setup.
    history = [_row(140000, 85000), _row(120000, 80000), _row(95000, 82000)]
    assert build_swing_signal("Gold", history) is None


def test_no_signal_on_stable():
    # weekly move tiny relative to position size -> "stable", not a reversal.
    history = [_row(100500, 80000), _row(100000, 80000), _row(95000, 82000)]
    assert build_swing_signal("Gold", history) is None


def test_no_signal_on_insufficient_history():
    assert build_swing_signal("Gold", [_row(100000, 80000)]) is None


def test_bearish_turn_on_reversal_against_bullish_trend():
    # newest-first: net had been building bullish over the window
    # (13000 -> 40000), THEN this most recent week dropped back to 25000 —
    # a bearish weekly move against a bullish multi-week trend.
    history = [_row(110000, 85000), _row(120000, 80000), _row(95000, 82000)]
    signal = build_swing_signal("Gold", history)
    assert signal is not None
    assert signal.direction == SwingDirection.BEARISH_TURN
    assert signal.weekly_change < 0
    assert signal.trend_score > 0


def test_bullish_turn_on_reversal_against_bearish_trend():
    # newest-first: net had been dropping over the window (30000 -> -20000),
    # THEN this most recent week jumped back up to 10000 — a bullish weekly
    # move against a bearish multi-week trend.
    history = [_row(95000, 85000), _row(80000, 100000), _row(90000, 60000)]
    signal = build_swing_signal("EUR/USD", history)
    assert signal is not None
    assert signal.direction == SwingDirection.BULLISH_TURN
    assert signal.weekly_change > 0
    assert signal.trend_score < 0


# --- news alignment ---

_BEARISH_TURN_HISTORY = [_row(110000, 85000), _row(120000, 80000), _row(95000, 82000)]


def test_news_confirms_bearish_turn():
    signal = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=-40.0)
    assert signal.news_alignment == NewsAlignment.CONFIRMS
    assert any("confirms" in e for e in signal.evidence)


def test_news_contradicts_bearish_turn():
    signal = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=40.0)
    assert signal.news_alignment == NewsAlignment.CONTRADICTS


def test_news_neutral_band():
    signal = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=5.0)
    assert signal.news_alignment == NewsAlignment.NEUTRAL


def test_news_no_data():
    signal = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=None)
    assert signal.news_alignment == NewsAlignment.NO_DATA
    assert any("No broad market news" in e for e in signal.evidence)


# --- confidence model ---

def test_confidence_news_confirms_scores_higher_than_no_data():
    confirmed = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=-40.0)
    no_data = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=None)
    assert confirmed.confidence > no_data.confidence


def test_confidence_news_contradicts_scores_lower_than_no_data():
    contradicted = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=40.0)
    no_data = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=None)
    assert contradicted.confidence < no_data.confidence


def test_confidence_clamped_0_100():
    # even with every bonus stacked, confidence never exceeds 100
    signal = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=-90.0)
    assert 0.0 <= signal.confidence <= 100.0


# --- headline() ---

def test_headline_mentions_asset_and_direction():
    signal = build_swing_signal("Gold", _BEARISH_TURN_HISTORY, news_sentiment_score_value=-40.0)
    headline = signal.headline()
    assert "Gold" in headline
    assert "BEARISH" in headline


# --- should_send_swing_alert ---

def test_should_alert_when_never_alerted_before():
    assert should_send_swing_alert(None, now=datetime.now(timezone.utc)) is True


def test_should_not_alert_again_before_next_cot_release():
    # "recorded_at" a moment ago -> no new Friday-3:30pm-ET release could
    # plausibly have happened yet in the same test run.
    now = datetime.now(timezone.utc)
    last_alerted = {"recorded_at": now.isoformat()}
    assert should_send_swing_alert(last_alerted, now=now) is False


def test_should_alert_again_after_a_full_week_has_passed():
    now = datetime.now(timezone.utc)
    long_ago = now - timedelta(days=10)
    last_alerted = {"recorded_at": long_ago.isoformat()}
    assert should_send_swing_alert(last_alerted, now=now) is True
