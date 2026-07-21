from datetime import datetime, timezone, timedelta

from agents.score_momentum import compute_score_momentum, explain_momentum
from models.trade_decision import Momentum


def _row(score, hours_ago):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return {"fundamental_score": score, "recorded_at": ts}


def test_no_history_is_insufficient():
    m = compute_score_momentum([], "fundamental_score", 79.0)
    assert m.momentum == Momentum.INSUFFICIENT_HISTORY


def test_spec_example_79_to_76_is_stable():
    history = [_row(79.0, hours_ago=1)]
    m = compute_score_momentum(history, "fundamental_score", 76.0)
    assert m.momentum == Momentum.STABLE


def test_spec_example_79_to_61_is_weakening():
    history = [_row(79.0, hours_ago=1)]
    m = compute_score_momentum(history, "fundamental_score", 61.0)
    assert m.momentum == Momentum.WEAKENING


def test_spec_example_79_to_42_is_major_deterioration():
    history = [_row(79.0, hours_ago=1)]
    m = compute_score_momentum(history, "fundamental_score", 42.0)
    assert m.momentum == Momentum.MAJOR_DETERIORATION


def test_spec_example_95_to_97_is_strengthening():
    history = [_row(95.0, hours_ago=1)]
    m = compute_score_momentum(history, "fundamental_score", 97.0)
    assert m.momentum == Momentum.STRENGTHENING


def test_windowed_changes_pick_closest_reading_at_or_before_cutoff():
    # Semantics: "change over the last Nh" compares against the most recent
    # reading that is AT LEAST N hours old (a reading from 30 minutes ago
    # doesn't represent a full hour of change) -- readings newer than the
    # cutoff are skipped, exactly like an "as of N hours ago" snapshot.
    history = [_row(50.0, hours_ago=0.5), _row(70.0, hours_ago=5), _row(80.0, hours_ago=30)]
    m = compute_score_momentum(history, "fundamental_score", 55.0)
    assert m.change_1h == -15.0    # 0.5h-ago reading is too recent to count; falls back to the 5h-ago reading (70)
    assert m.change_4h == -15.0    # same: nothing between 1h and 4h ago, still the 5h-ago reading
    assert m.change_24h == -25.0   # 5h-ago reading is too recent for a 24h window; falls back to the 30h-ago reading (80)


def test_explain_momentum_uses_risks_when_weakening():
    explanation = explain_momentum(Momentum.WEAKENING, catalysts=["good thing"], risks=["Treasury yields increased"])
    assert explanation == ["Treasury yields increased"]


def test_explain_momentum_uses_catalysts_when_strengthening():
    explanation = explain_momentum(Momentum.STRENGTHENING, catalysts=["Commercial hedgers building length"], risks=["bad thing"])
    assert explanation == ["Commercial hedgers building length"]
