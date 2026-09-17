from agents.cycle_health import assess_cycle_health, DEGRADED_CONFIDENCE_THRESHOLD


def _healthy(n):
    return [{"error": None, "confidence_score": 70.0} for _ in range(n)]


def _degraded(n):
    return [{"error": None, "confidence_score": 0.0} for _ in range(n)]


def _errored(n):
    return [{"error": "boom"} for _ in range(n)]


def test_empty_results_returns_healthy_zero_state():
    result = assess_cycle_health([])
    assert result.total_entries == 0
    assert result.is_systemic_issue is False
    assert result.reasons == []


def test_all_healthy_is_not_systemic():
    result = assess_cycle_health(_healthy(20))
    assert result.healthy_count == 20
    assert result.is_systemic_issue is False


def test_a_few_degraded_entries_is_normal_not_systemic():
    """A couple of tickers with bad data this cycle is routine, not alarming."""
    results = _healthy(18) + _degraded(2)
    result = assess_cycle_health(results)
    assert result.degraded_count == 2
    assert result.is_systemic_issue is False


def test_most_entries_degraded_is_flagged_systemic():
    """The core scenario this module exists to catch: everything
    'succeeds' but returns near-zero confidence across the board."""
    result = assess_cycle_health(_degraded(20))
    assert result.is_systemic_issue is True
    assert any("near-zero confidence" in r for r in result.reasons)
    assert any("shared cause" in r for r in result.reasons)


def test_high_error_rate_flagged_systemic_even_with_low_degradation():
    results = _healthy(15) + _errored(10)
    result = assess_cycle_health(results)
    assert result.error_count == 10
    assert result.is_systemic_issue is True
    assert any("hard-crashed" in r for r in result.reasons)


def test_low_error_rate_alone_is_not_systemic():
    results = _healthy(18) + _errored(2)
    result = assess_cycle_health(results)
    assert result.is_systemic_issue is False


def test_confidence_exactly_at_threshold_is_not_counted_as_degraded():
    results = [{"error": None, "confidence_score": DEGRADED_CONFIDENCE_THRESHOLD}]
    result = assess_cycle_health(results)
    assert result.degraded_count == 0
    assert result.healthy_count == 1


def test_confidence_just_below_threshold_is_degraded():
    results = [{"error": None, "confidence_score": DEGRADED_CONFIDENCE_THRESHOLD - 0.1}]
    result = assess_cycle_health(results)
    assert result.degraded_count == 1


def test_both_error_and_degradation_reasons_can_appear_together():
    results = _errored(6) + _degraded(11) + _healthy(3)  # 20 total: 30% errors, 55% degraded
    result = assess_cycle_health(results)
    assert result.is_systemic_issue is True
    assert len(result.reasons) == 2


def test_to_dict_serializes_all_fields():
    result = assess_cycle_health(_healthy(5))
    d = result.to_dict()
    assert d["total_entries"] == 5
    assert d["is_systemic_issue"] is False
    assert "reasons" in d


def test_missing_confidence_score_field_treated_as_zero_not_crashed_on():
    """A malformed result dict (missing confidence_score entirely)
    shouldn't crash — treated as maximally degraded (0.0), the safe default."""
    results = [{"error": None}]
    result = assess_cycle_health(results)
    assert result.degraded_count == 1
