from agents.positioning_scoring import net_position_trend_score, positioning_extremity_flag


def _row(long_, short_, oi=500000, date="2026-07-01"):
    return {"noncomm_long": str(long_), "noncomm_short": str(short_), "open_interest": str(oi), "report_date": date}


def test_building_net_length_gives_positive_score():
    # newest first: net went from (95000-82000)=13000 up to (120000-80000)=40000
    history = [_row(120000, 80000), _row(105000, 81000), _row(95000, 82000)]
    score = net_position_trend_score(history)
    assert score is not None
    assert score > 0


def test_reducing_net_length_gives_negative_score():
    history = [_row(80000, 100000), _row(90000, 95000), _row(100000, 85000)]
    score = net_position_trend_score(history)
    assert score is not None
    assert score < 0


def test_flat_positioning_gives_near_zero_score():
    history = [_row(100000, 80000), _row(100000, 80000), _row(100000, 80000)]
    score = net_position_trend_score(history)
    assert score == 0.0


def test_insufficient_history_returns_none():
    history = [_row(100000, 80000)]
    assert net_position_trend_score(history) is None


def test_malformed_rows_are_skipped():
    history = [_row(120000, 80000), {"noncomm_long": None}, _row(95000, 82000)]
    score = net_position_trend_score(history)
    assert score is not None


def test_crowded_long_flagged_above_threshold():
    row = _row(300000, 50000, oi=500000)  # net = 250000, 50% of OI
    assert positioning_extremity_flag(row) == "crowded_long"


def test_crowded_short_flagged_below_threshold():
    row = _row(50000, 300000, oi=500000)  # net = -250000, -50% of OI
    assert positioning_extremity_flag(row) == "crowded_short"


def test_balanced_positioning_not_flagged():
    row = _row(110000, 100000, oi=500000)  # net = 10000, 2% of OI
    assert positioning_extremity_flag(row) is None


def test_zero_open_interest_returns_none_safely():
    row = _row(100000, 80000, oi=0)
    assert positioning_extremity_flag(row) is None
