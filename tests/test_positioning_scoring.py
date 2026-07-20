from agents.positioning_scoring import net_position_trend_score, positioning_extremity_flag


def _row(long_, short_, oi=500000, date="2026-07-01", comm_long=None, comm_short=None):
    row = {"noncomm_long": str(long_), "noncomm_short": str(short_), "open_interest": str(oi), "report_date": date}
    if comm_long is not None:
        row["comm_long"] = str(comm_long)
    if comm_short is not None:
        row["comm_short"] = str(comm_short)
    return row


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


def test_commercial_trend_scored_via_long_short_key_params():
    # Commercials building net length: net grows 13000 -> 40000
    history = [
        _row(999, 999, comm_long=120000, comm_short=80000),
        _row(999, 999, comm_long=105000, comm_short=92000),
        _row(999, 999, comm_long=95000, comm_short=82000),
    ]
    score = net_position_trend_score(history, long_key="comm_long", short_key="comm_short")
    assert score is not None
    assert score > 0


def test_commercial_trend_independent_of_speculative_trend():
    # Speculators reducing length while commercials build it -> opposite signs
    history = [
        _row(80000, 100000, comm_long=140000, comm_short=70000),
        _row(90000, 95000, comm_long=110000, comm_short=90000),
        _row(100000, 85000, comm_long=95000, comm_short=95000),
    ]
    spec_score = net_position_trend_score(history, long_key="noncomm_long", short_key="noncomm_short")
    comm_score = net_position_trend_score(history, long_key="comm_long", short_key="comm_short")
    assert spec_score is not None and comm_score is not None
    assert spec_score < 0 < comm_score


def test_missing_commercial_fields_returns_none_not_error():
    history = [_row(100000, 80000), _row(95000, 82000)]  # no comm_long/comm_short at all
    score = net_position_trend_score(history, long_key="comm_long", short_key="comm_short")
    assert score is None
