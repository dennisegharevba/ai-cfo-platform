from datetime import date, timedelta

from agents.strategy_backtest import simulate_strategy, TradeRecord, StrategyBacktestResult


def _flat_prices_with_pattern(base, n, forward_days, returns_pct):
    """Builds price anchor pairs (entry, exit) for n trades spaced 30
    days apart, each with an explicitly controlled % return."""
    prices = []
    for i in range(n):
        entry = base + timedelta(days=i * 30)
        exit_ = entry + timedelta(days=forward_days)
        prices.append((entry, 100.0))
        prices.append((exit_, 100.0 * (1 + returns_pct[i % len(returns_pct)] / 100)))
    prices.sort()
    return prices


def test_below_threshold_signal_produces_no_trade():
    base = date(2020, 1, 1)
    signal_scores = [(base, 5.0)]  # below the default entry_threshold of 15.0
    prices = [(base, 100.0), (base + timedelta(days=20), 110.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices)
    assert result.num_trades == 0
    assert result.skipped_dates == 1


def test_bullish_signal_with_rising_price_is_a_winning_long_trade():
    base = date(2020, 1, 1)
    signal_scores = [(base, 40.0)]
    prices = [(base, 100.0), (base + timedelta(days=20), 105.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=5.0)
    t = result.trades[0]
    assert t.direction == "long"
    assert t.gross_return_pct == 5.0
    assert t.net_return_pct == 4.95  # 5.0 - 0.05 round-trip cost
    assert t.is_win is True


def test_bearish_signal_with_falling_price_is_a_winning_short_trade():
    base = date(2020, 1, 1)
    signal_scores = [(base, -40.0)]
    prices = [(base, 100.0), (base + timedelta(days=20), 95.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=5.0)
    t = result.trades[0]
    assert t.direction == "short"
    assert t.gross_return_pct == 5.0  # inverted: price fell 5%, short gains 5%
    assert t.is_win is True


def test_bullish_signal_with_falling_price_is_a_losing_long_trade():
    base = date(2020, 1, 1)
    signal_scores = [(base, 40.0)]
    prices = [(base, 100.0), (base + timedelta(days=20), 95.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices)
    t = result.trades[0]
    assert t.gross_return_pct == -5.0
    assert t.is_win is False


def test_missing_forward_price_is_skipped_not_fabricated():
    base = date(2020, 1, 1)
    signal_scores = [(base, 40.0)]
    prices = [(base, 100.0)]  # no price 20 days later at all
    result = simulate_strategy("Test", "TEST", signal_scores, prices)
    assert result.num_trades == 0
    assert result.skipped_dates == 1


def test_total_return_compounds_not_sums():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 2, 20, [10.0, 10.0])
    signal_scores = [(base, 40.0), (base + timedelta(days=30), 40.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    # Compounded: 1.10 * 1.10 = 1.21 -> +21%, NOT the naive sum of +20%.
    assert result.total_return_pct == 21.0


def test_win_rate_and_profit_factor_computed_correctly():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 4, 20, [10.0, 10.0, -5.0, 10.0])
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(4)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert result.num_wins == 3
    assert result.num_losses == 1
    assert result.win_rate == 75.0
    # profit_factor = sum(wins) / abs(sum(losses)) = 30 / 5 = 6.0
    assert result.profit_factor == 6.0


def test_profit_factor_none_when_no_losses_exist():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 3, 20, [5.0, 5.0, 5.0])
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(3)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert result.num_losses == 0
    assert result.profit_factor is None  # undefined, not fabricated as infinite


def test_sharpe_and_sortino_none_for_fewer_than_two_trades():
    base = date(2020, 1, 1)
    signal_scores = [(base, 40.0)]
    prices = [(base, 100.0), (base + timedelta(days=20), 105.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices)
    assert result.sharpe_ratio is None
    assert result.sortino_ratio is None


def test_sharpe_none_for_zero_variance_not_fabricated_as_infinite():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 5, 20, [3.0, 3.0, 3.0, 3.0, 3.0])  # identical every time
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(5)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert result.sharpe_ratio is None


def test_sharpe_computed_correctly_with_real_variance():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 6, 20, [3.0, 2.0, -1.0, 4.0, 1.0, -2.0])
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(6)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert result.sharpe_ratio is not None
    import statistics
    returns = [3.0, 2.0, -1.0, 4.0, 1.0, -2.0]
    expected_sharpe = round((statistics.mean(returns) / statistics.stdev(returns)) * ((252 / 20) ** 0.5), 2)
    assert result.sharpe_ratio == expected_sharpe


def test_max_drawdown_reflects_the_strategy_equity_curve_not_the_asset():
    """A strategy that only takes winning trades should show ~0 drawdown
    even if the underlying asset itself had a real drawdown somewhere in
    its history — this is a property of the STRATEGY's own equity curve."""
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 3, 20, [5.0, 5.0, 5.0])
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(3)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert result.max_drawdown_pct == 0.0


def test_max_drawdown_negative_when_a_losing_trade_occurs():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 3, 20, [5.0, -10.0, 5.0])
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(3)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert result.max_drawdown_pct < 0


def test_interpretation_flags_small_sample():
    base = date(2020, 1, 1)
    signal_scores = [(base, 40.0)]
    prices = [(base, 100.0), (base + timedelta(days=20), 105.0)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices)
    assert "too few" in result.interpretation().lower()


def test_interpretation_notes_no_losses_case():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 6, 20, [5.0] * 6)
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(6)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    assert "undefined, not infinite" in result.interpretation()


def test_to_dict_serializes_all_fields():
    base = date(2020, 1, 1)
    prices = _flat_prices_with_pattern(base, 6, 20, [3.0, 2.0, -1.0, 4.0, 1.0, -2.0])
    signal_scores = [(base + timedelta(days=i * 30), 40.0) for i in range(6)]
    result = simulate_strategy("Test", "TEST", signal_scores, prices)
    d = result.to_dict()
    assert d["num_trades"] == 6
    assert "sharpe_ratio" in d
    assert "max_drawdown_pct" in d


def test_transaction_costs_are_genuinely_subtracted():
    base = date(2020, 1, 1)
    signal_scores = [(base, 40.0)]
    prices = [(base, 100.0), (base + timedelta(days=20), 105.0)]
    result_no_cost = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=0.0)
    result_with_cost = simulate_strategy("Test", "TEST", signal_scores, prices, transaction_cost_bps=50.0)
    assert result_with_cost.trades[0].net_return_pct < result_no_cost.trades[0].net_return_pct
    assert result_with_cost.trades[0].net_return_pct == 5.0 - 0.5  # 50bps = 0.5%
