from agents.circuit_breaker import check_circuit_breaker, CircuitBreakerConfig


def test_no_breach_on_a_normal_day():
    result = check_circuit_breaker(current_equity=99000, daily_starting_equity=100000, peak_equity=105000)
    assert result.should_halt is False
    assert result.reasons == []


def test_no_breach_on_a_gain_day():
    result = check_circuit_breaker(current_equity=110000, daily_starting_equity=100000, peak_equity=110000)
    assert result.should_halt is False
    assert result.daily_pnl_pct == 10.0


def test_daily_loss_breach_triggers_halt():
    result = check_circuit_breaker(
        current_equity=94000, daily_starting_equity=100000, peak_equity=105000,
        config=CircuitBreakerConfig(max_daily_loss_pct=5.0),
    )
    assert result.should_halt is True
    assert "daily loss" in result.reasons[0].lower()


def test_daily_loss_exactly_at_threshold_triggers_halt():
    """The boundary case: exactly -5.0% with a 5.0% limit should trigger
    (>=), not require exceeding it."""
    result = check_circuit_breaker(
        current_equity=95000, daily_starting_equity=100000, peak_equity=105000,
        config=CircuitBreakerConfig(max_daily_loss_pct=5.0),
    )
    assert result.daily_pnl_pct == -5.0
    assert result.should_halt is True


def test_daily_loss_just_under_threshold_does_not_trigger():
    result = check_circuit_breaker(
        current_equity=95001, daily_starting_equity=100000, peak_equity=105000,
        config=CircuitBreakerConfig(max_daily_loss_pct=5.0),
    )
    assert result.should_halt is False


def test_total_drawdown_breach_triggers_halt_independent_of_daily_pnl():
    """A slow bleed over many days — daily loss is small, but the total
    drawdown from peak is large — must still trigger."""
    result = check_circuit_breaker(
        current_equity=89000, daily_starting_equity=89500, peak_equity=105000,
        config=CircuitBreakerConfig(max_total_drawdown_pct=15.0),
    )
    assert result.should_halt is True
    assert "drawdown" in result.reasons[0].lower()


def test_both_breaches_simultaneously_report_both_reasons():
    result = check_circuit_breaker(
        current_equity=85000, daily_starting_equity=100000, peak_equity=105000,
        config=CircuitBreakerConfig(max_daily_loss_pct=5.0, max_total_drawdown_pct=15.0),
    )
    assert result.should_halt is True
    assert len(result.reasons) == 2


def test_zero_daily_starting_equity_does_not_divide_by_zero():
    result = check_circuit_breaker(current_equity=1000, daily_starting_equity=0, peak_equity=1000)
    assert result.daily_pnl_pct == 0.0  # degraded gracefully, not a crash


def test_zero_peak_equity_does_not_divide_by_zero():
    result = check_circuit_breaker(current_equity=1000, daily_starting_equity=1000, peak_equity=0)
    assert result.drawdown_from_peak_pct == 0.0


def test_custom_config_thresholds_respected():
    tight_config = CircuitBreakerConfig(max_daily_loss_pct=1.0, max_total_drawdown_pct=2.0)
    result = check_circuit_breaker(current_equity=98500, daily_starting_equity=100000, peak_equity=100000, config=tight_config)
    assert result.should_halt is True  # -1.5% breaches a 1% limit
