from datetime import date, timedelta
from unittest.mock import patch

from agents.swing_signal_backtest import swing_signal_history


def _row(long_, short_, report_date):
    return {"noncomm_long": str(long_), "noncomm_short": str(short_), "report_date": report_date}


# Oldest-first weekly history: net builds bullish (13000 -> 40000), then
# the third week drops sharply back to 25000 — a genuine reversal_watch
# against the bullish trend. Same underlying numbers as
# tests/test_swing_signal.py's _BEARISH_TURN_HISTORY, just re-ordered
# oldest-first (as a real CFTC history arrives) and dated.
_BEARISH_REVERSAL_OLDEST_FIRST = [
    _row(95000, 82000, "2020-01-03"),   # net 13000
    _row(120000, 80000, "2020-01-10"),  # net 40000
    _row(110000, 85000, "2020-01-17"),  # net 25000  <- reversal week
    _row(108000, 85000, "2020-01-24"),  # net 23000  <- continuation (bearish, agrees w/ new trend), no signal
]

# Oldest-first: net drops bearish (30000 -> -20000), then the third week
# jumps back up to 10000 — a bullish reversal_watch. Same numbers as
# test_swing_signal.py's bullish fixture, oldest-first + dated.
_BULLISH_REVERSAL_OLDEST_FIRST = [
    _row(90000, 60000, "2021-01-01"),  # net 30000
    _row(80000, 100000, "2021-01-08"),  # net -20000
    _row(95000, 85000, "2021-01-15"),  # net 10000  <- reversal week
]


def test_walks_history_and_detects_known_reversal_at_correct_date():
    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=_BEARISH_REVERSAL_OLDEST_FIRST):
        results = swing_signal_history(
            "Gold", "GOLD - COMMODITY EXCHANGE INC.",
            start_date=date(2020, 1, 1), end_date=date(2020, 1, 31), window_weeks=3,
        )

    assert len(results) == 1
    d, score = results[0]
    assert d == date(2020, 1, 17)  # the reversal week, not the continuation week after it
    assert score < 0  # bearish turn -> negative signed confidence
    assert 0 < abs(score) <= 100


def test_bullish_turn_gets_positive_score():
    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=_BULLISH_REVERSAL_OLDEST_FIRST):
        results = swing_signal_history(
            "EUR/USD", "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            start_date=date(2021, 1, 15), end_date=date(2021, 1, 15), window_weeks=3,
        )

    assert len(results) == 1
    d, score = results[0]
    assert d == date(2021, 1, 15)
    assert score > 0  # bullish turn -> positive signed confidence


def test_no_signal_on_pure_continuation_history():
    # Net position just keeps building in the same direction, week over
    # week, the whole way through — never a reversal, so never a signal.
    continuation = [
        _row(50000, 80000, "2020-01-03"),   # net -30000
        _row(40000, 85000, "2020-01-10"),   # net -45000
        _row(30000, 90000, "2020-01-17"),   # net -60000
        _row(20000, 95000, "2020-01-24"),   # net -75000
    ]
    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=continuation):
        results = swing_signal_history(
            "Gold", "GOLD - COMMODITY EXCHANGE INC.",
            start_date=date(2020, 1, 1), end_date=date(2020, 1, 31), window_weeks=3,
        )
    assert results == []


def test_returns_empty_list_when_underlying_fetch_returns_none():
    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=None):
        results = swing_signal_history(
            "Gold", "GOLD - COMMODITY EXCHANGE INC.",
            start_date=date(2020, 1, 1), end_date=date(2020, 1, 31),
        )
    assert results == []


def test_excludes_signal_dates_outside_the_requested_range():
    # The reversal week (2020-01-17) is used to build later windows via
    # the buffer, but a caller asking for results starting 2020-01-18
    # onward should never see a signal dated before that.
    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=_BEARISH_REVERSAL_OLDEST_FIRST):
        results = swing_signal_history(
            "Gold", "GOLD - COMMODITY EXCHANGE INC.",
            start_date=date(2020, 1, 18), end_date=date(2020, 1, 31), window_weeks=3,
        )
    assert results == []


def test_fetches_with_a_leading_buffer_before_start_date():
    """Without a buffer, the first window_weeks-1 of the requested range
    would be silently untestable (no prior history to build a window
    from) — verified directly that the underlying fetch is asked for
    data starting well before the requested start_date."""
    start_date = date(2020, 6, 1)
    end_date = date(2020, 12, 31)
    window_weeks = 8

    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=None) as mock_fetch:
        swing_signal_history("Gold", "GOLD - COMMODITY EXCHANGE INC.", start_date, end_date, window_weeks=window_weeks)

    args, _ = mock_fetch.call_args
    _market, fetch_start, fetch_end = args
    assert fetch_start == start_date - timedelta(weeks=window_weeks * 2)
    assert fetch_end == end_date


def test_skips_rows_with_unparseable_or_missing_dates():
    bad_history = [
        _row(95000, 82000, None),
        _row(120000, 80000, "not-a-date"),
        _row(110000, 85000, "2020-01-17"),
    ]
    with patch("agents.swing_signal_backtest.fetch_cot_history_range", return_value=bad_history):
        # Only one row has a valid date, well under window_weeks=3 -> nothing testable, no crash.
        results = swing_signal_history(
            "Gold", "GOLD - COMMODITY EXCHANGE INC.",
            start_date=date(2020, 1, 1), end_date=date(2020, 1, 31), window_weeks=3,
        )
    assert results == []
