from agents.portfolio_construction import (
    fixed_fractional_size, kelly_fraction, kelly_fraction_from_backtest,
    volatility_target_weights, apply_position_constraints,
)
from agents.strategy_backtest import StrategyBacktestResult, TradeRecord
from datetime import date


# --- fixed_fractional_size ---

def test_fixed_fractional_size_hand_verified():
    # $100k account, risk 1%, entry 100, stop 95 -> risk $1000 / $5 per unit = 200 units
    assert fixed_fractional_size(100000, 1.0, 100.0, 95.0) == 200.0


def test_fixed_fractional_size_none_when_entry_equals_stop():
    assert fixed_fractional_size(100000, 1.0, 100.0, 100.0) is None


def test_fixed_fractional_size_works_for_short_stop_above_entry():
    # A short: stop ABOVE entry. Risk distance should still be the absolute difference.
    assert fixed_fractional_size(100000, 1.0, 100.0, 105.0) == 200.0


# --- kelly_fraction ---

def test_kelly_fraction_matches_the_classic_textbook_example():
    # 60% win rate, 1:1 payoff -> raw Kelly = 0.6 - 0.4/1 = 0.20 (20%)
    assert kelly_fraction(60.0, 1.0, 1.0, kelly_multiplier=1.0) == 20.0


def test_kelly_fraction_applies_the_fractional_multiplier():
    assert kelly_fraction(60.0, 1.0, 1.0, kelly_multiplier=0.25) == 5.0


def test_kelly_fraction_clamps_negative_edge_to_zero_not_negative():
    # 30% win rate, 1:1 payoff -> raw Kelly = 0.3 - 0.7/1 = -0.4 (a losing edge)
    assert kelly_fraction(30.0, 1.0, 1.0) == 0.0


def test_kelly_fraction_none_when_avg_loss_is_zero():
    assert kelly_fraction(60.0, 1.0, 0.0) is None


def test_kelly_fraction_none_for_invalid_win_rate():
    assert kelly_fraction(150.0, 1.0, 1.0) is None
    assert kelly_fraction(-10.0, 1.0, 1.0) is None


def test_kelly_fraction_scales_correctly_with_a_better_payoff_ratio():
    # A 2:1 payoff ratio at the same win rate should require a smaller
    # edge to justify the same or larger bet size than a 1:1 payoff.
    kelly_1to1 = kelly_fraction(40.0, 1.0, 1.0, kelly_multiplier=1.0)
    kelly_2to1 = kelly_fraction(40.0, 2.0, 1.0, kelly_multiplier=1.0)
    assert kelly_2to1 > kelly_1to1


# --- kelly_fraction_from_backtest ---

def _trade(net_return_pct):
    return TradeRecord(
        entry_date=date(2024, 1, 1), exit_date=date(2024, 1, 21), direction="long",
        signal_score_at_entry=40.0, gross_return_pct=net_return_pct, net_return_pct=net_return_pct,
        is_win=net_return_pct > 0,
    )


def test_kelly_from_backtest_none_for_fewer_than_five_trades():
    result = StrategyBacktestResult(
        signal_name="Test", asset="TEST", entry_threshold=15.0, forward_window_days=20,
        transaction_cost_bps=5.0, trades=[_trade(3.0), _trade(-1.0)],
    )
    assert kelly_fraction_from_backtest(result) is None


def test_kelly_from_backtest_none_when_no_losing_trades():
    result = StrategyBacktestResult(
        signal_name="Test", asset="TEST", entry_threshold=15.0, forward_window_days=20,
        transaction_cost_bps=5.0, trades=[_trade(3.0)] * 6,
    )
    assert kelly_fraction_from_backtest(result) is None


def test_kelly_from_backtest_computes_a_real_value_from_real_trades():
    # 6 trades: 4 wins of +3%, 2 losses of -2% -> win_rate=66.7%, avg_win=3.0, avg_loss=2.0
    trades = [_trade(3.0)] * 4 + [_trade(-2.0)] * 2
    result = StrategyBacktestResult(
        signal_name="Test", asset="TEST", entry_threshold=15.0, forward_window_days=20,
        transaction_cost_bps=5.0, trades=trades,
    )
    kelly = kelly_fraction_from_backtest(result, kelly_multiplier=1.0)
    assert kelly is not None
    # Hand-verify: W=0.6667, R=3.0/2.0=1.5 -> f* = 0.6667 - 0.3333/1.5 = 0.4444 -> 44.44%
    assert abs(kelly - 44.44) < 0.5


# --- volatility_target_weights ---

def test_volatility_target_weights_inverse_relationship():
    # Gold vol=15 is HALF of SPY vol=30 -> Gold should get exactly 2x SPY's weight
    weights = volatility_target_weights({"Gold": 15.0, "SPY": 30.0})
    assert abs(weights["Gold"] - weights["SPY"] * 2) < 0.02  # 0.02 tolerance: the code's own 2-decimal rounding can introduce up to ~0.01 here


def test_volatility_target_weights_sum_to_100():
    weights = volatility_target_weights({"Gold": 15.0, "SPY": 30.0, "TLT": 8.0})
    assert abs(sum(weights.values()) - 100.0) < 0.01


def test_volatility_target_weights_excludes_zero_or_negative_vol_not_fabricated():
    weights = volatility_target_weights({"Gold": 15.0, "Broken": 0.0, "AlsoNegative": -5.0})
    assert "Broken" not in weights
    assert "AlsoNegative" not in weights
    assert weights["Gold"] == 100.0  # the only usable asset gets the full allocation


def test_volatility_target_weights_empty_input_returns_empty():
    assert volatility_target_weights({}) == {}
    assert volatility_target_weights({"A": 0.0}) == {}


# --- apply_position_constraints ---

def test_constraints_caps_individual_position():
    result = apply_position_constraints({"A": 80.0, "B": 10.0}, max_position_pct=25.0, max_gross_exposure_pct=100.0)
    assert result["A"] == 25.0
    assert result["B"] == 10.0  # untouched — under both the individual cap AND the gross total is under budget


def test_constraints_does_not_force_fill_unused_gross_budget():
    """Capping a large position creates slack — this function does NOT
    redistribute that slack into other positions to fully use the gross
    budget. That's a deliberate, documented design choice (leaving
    capital in cash is the conservative default), not a bug."""
    result = apply_position_constraints({"A": 80.0, "B": 10.0}, max_position_pct=25.0, max_gross_exposure_pct=100.0)
    assert sum(result.values()) == 35.0  # 25 + 10, well under the 100 gross budget — left as-is


def test_constraints_rescales_down_when_still_over_budget_after_capping():
    # 5 positions at 30 each, capped to 25 each = 125 total, still exceeds 100 -> rescale down
    result = apply_position_constraints(
        {"A": 30.0, "B": 30.0, "C": 30.0, "D": 30.0, "E": 30.0}, max_position_pct=25.0, max_gross_exposure_pct=100.0,
    )
    assert abs(sum(result.values()) - 100.0) < 0.01
    assert all(abs(w - 20.0) < 0.01 for w in result.values())  # all equal, all scaled down proportionally


def test_constraints_permits_leverage_when_explicitly_configured():
    result = apply_position_constraints({"A": 60.0, "B": 60.0}, max_position_pct=100.0, max_gross_exposure_pct=150.0)
    assert abs(sum(result.values()) - 120.0) < 0.01  # under 150, no rescale needed
