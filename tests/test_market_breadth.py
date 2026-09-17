from agents.market_breadth import compute_breadth


def _uptrend(n=60, base=100.0):
    return list(reversed([{"close": base + i * 0.5} for i in range(n)]))


def _downtrend(n=60, base=200.0):
    return list(reversed([{"close": base - i * 0.5} for i in range(n)]))


def test_empty_universe_returns_zeros():
    result = compute_breadth({})
    assert result.universe_size == 0
    assert result.usable_count == 0
    assert result.pct_above_50dma is None
    assert result.advance_decline_ratio is None


def test_all_advancers_correctly_counted():
    histories = {"A": _uptrend(), "B": _uptrend(), "C": _uptrend()}
    result = compute_breadth(histories)
    assert result.advancers == 3
    assert result.decliners == 0
    assert result.advance_decline_ratio == float("inf")


def test_mixed_advancers_and_decliners():
    histories = {"A": _uptrend(), "B": _downtrend()}
    result = compute_breadth(histories)
    assert result.advancers == 1
    assert result.decliners == 1
    assert result.advance_decline_ratio == 1.0


def test_pct_above_50dma_reflects_real_trend():
    histories = {"A": _uptrend(), "B": _uptrend(), "C": _downtrend()}
    result = compute_breadth(histories)
    # Uptrends: latest close is above a rising 50DMA. Downtrend: latest
    # close is below a falling 50DMA.
    assert result.pct_above_50dma == 66.7


def test_insufficient_history_excluded_not_estimated():
    histories = {"A": _uptrend(), "B": [{"close": 100.0}], "C": []}
    result = compute_breadth(histories)
    assert result.universe_size == 3
    assert result.usable_count == 1  # only A has >= 2 closes


def test_malformed_rows_are_skipped_not_crashed_on():
    histories = {"A": [{"close": 100.0}, {"no_close": True}, {"close": 105.0}]}
    result = compute_breadth(histories)
    assert result.usable_count == 1


def test_new_highs_and_lows_reflect_the_fetched_window():
    # A strictly rising series: the latest close is both the window's max
    # (a "new high" within this window) by construction.
    histories = {"A": _uptrend()}
    result = compute_breadth(histories)
    assert result.new_highs == 1
    assert result.new_lows == 0


def test_window_days_reflects_actual_history_length():
    histories = {"A": _uptrend(n=45)}
    result = compute_breadth(histories)
    assert result.window_days == 45


def test_unchanged_counted_separately_from_advance_decline():
    flat = list(reversed([{"close": 100.0} for _ in range(10)]))
    histories = {"A": flat}
    result = compute_breadth(histories)
    assert result.unchanged == 1
    assert result.advancers == 0
    assert result.decliners == 0


def test_to_dict_serializes_all_fields():
    histories = {"A": _uptrend()}
    result = compute_breadth(histories)
    d = result.to_dict()
    assert d["usable_count"] == 1
    assert "advance_decline_ratio" in d
    assert "pct_above_50dma" in d
