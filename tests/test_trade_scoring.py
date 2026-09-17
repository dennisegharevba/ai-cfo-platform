from models.report import AgentReport, Bias, RiskLevel
from models.trade_decision import ExecutionRating
from agents import trade_scoring


def _report(department, bias_score, confidence=80.0, risk_level=RiskLevel.MODERATE, catalysts=None, risks=None, evidence=None):
    return AgentReport(
        department=department, asset_or_theme="TEST", bias=Bias.NEUTRAL, bias_score=bias_score,
        confidence=confidence, risk_level=risk_level, catalysts=catalysts or [], risks=risks or [],
        evidence=evidence or [],
    )


def test_fundamental_score_averages_only_fundamental_departments():
    reports = [
        _report("Chief Macro Officer", 40),
        _report("Chief Commodity Analyst", 40),
        _report("Chief Technical Officer", 100),  # must be excluded from fundamental
    ]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert score == 70.0  # bias_score 40 -> 70 on the 0-100 scale, both agree
    assert "Chief Technical Officer" not in contributing
    assert set(contributing) == {"Chief Macro Officer", "Chief Commodity Analyst"}


def test_fundamental_score_defaults_neutral_with_no_usable_reports():
    reports = [_report("Chief Macro Officer", 40, confidence=0.0)]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert score == 50.0
    assert contributing == []


def test_fundamental_score_includes_commodity_fundamentals_officer():
    """
    Regression test: FUNDAMENTAL_DEPARTMENTS was originally built before
    Chief Commodity Fundamentals Officer existed and silently excluded it
    even when present — a real gap, since this is exactly the department
    that carries gold/commodity fundamentals (real yields, dollar index,
    Fed funds rate) into this engine's Fundamental Score.
    """
    reports = [_report("Chief Commodity Fundamentals Officer", 60)]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert "Chief Commodity Fundamentals Officer" in contributing
    assert score == 80.0  # bias_score 60 -> 80 on the 0-100 scale


def test_fundamental_score_includes_seasonality_officer():
    reports = [_report("Chief Seasonality Officer", 20)]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert "Chief Seasonality Officer" in contributing


def test_fundamental_score_still_includes_macro_and_equity():
    """Direct proof that Chief Macro Officer and Chief Equity Analyst —
    the departments explicitly asked to be prioritized — are genuinely
    part of this engine's Fundamental Score."""
    reports = [_report("Chief Macro Officer", 50), _report("Chief Equity Analyst", 50)]
    score, contributing, excluded = trade_scoring.fundamental_score(reports)
    assert {"Chief Macro Officer", "Chief Equity Analyst"} <= set(contributing)
    assert excluded == []


def test_technical_score_maps_bias_score():
    tech = _report("Chief Technical Officer", 60)
    score, contributing, excluded = trade_scoring.technical_score(tech)
    assert score == 80.0
    assert contributing == ["Chief Technical Officer"]


def test_technical_score_neutral_when_missing():
    score, contributing, excluded = trade_scoring.technical_score(None)
    assert score == 50.0
    assert excluded == ["Chief Technical Officer"]


# --- technical_score_from_price_history (the real, live-data replacement) ---

def _bullish_history(n=60):
    return list(reversed([{"close": 100 + i * 1.5, "date": f"2026-01-{(i % 28) + 1:02d}"} for i in range(n)]))


def _bearish_history(n=60):
    return list(reversed([{"close": 300 - i * 1.5, "date": f"2026-01-{(i % 28) + 1:02d}"} for i in range(n)]))


def test_technical_score_from_price_history_bullish_uptrend():
    score, contributing, excluded = trade_scoring.technical_score_from_price_history(_bullish_history())
    assert score > 50.0
    assert contributing == ["Technical (price history)"]
    assert excluded == []


def test_technical_score_from_price_history_bearish_downtrend():
    score, contributing, excluded = trade_scoring.technical_score_from_price_history(_bearish_history())
    assert score < 50.0


def test_technical_score_from_price_history_empty_is_honest_neutral():
    score, contributing, excluded = trade_scoring.technical_score_from_price_history([])
    assert score == 50.0
    assert contributing == []
    assert excluded == ["Technical (price history)"]


def test_technical_score_from_price_history_insufficient_data_degrades_gracefully():
    # Only 1 close — not enough for any of the three indicators
    score, contributing, excluded = trade_scoring.technical_score_from_price_history([{"close": 100.0}])
    assert score == 50.0
    assert excluded == ["Technical (price history)"]


def test_technical_score_from_price_history_never_crashes_on_malformed_rows():
    history = [{"close": 100.0}, {"no_close_field": True}, {"close": 105.0}]
    score, contributing, excluded = trade_scoring.technical_score_from_price_history(history)
    # Should not raise — malformed rows are simply skipped
    assert isinstance(score, float)


# --- build_synthetic_technical_report ---

def _realistic_uptrend_history(n=60):
    """A gently rising series with noise (not a perfectly linear ramp,
    which would produce a zero MACD histogram per this codebase's own
    documented 'MACD measures acceleration, not trend existence' note)."""
    import math
    return list(reversed([
        {"close": 100 + i * 1.2 + math.sin(i * 0.5) * 2, "date": f"2026-01-{(i % 28) + 1:02d}"}
        for i in range(n)
    ]))


def _realistic_downtrend_history(n=60):
    import math
    return list(reversed([
        {"close": 300 - i * 1.2 + math.sin(i * 0.5) * 2, "date": f"2026-01-{(i % 28) + 1:02d}"}
        for i in range(n)
    ]))


def test_build_synthetic_technical_report_none_for_empty_history():
    assert trade_scoring.build_synthetic_technical_report([]) is None


def test_build_synthetic_technical_report_none_for_insufficient_history():
    assert trade_scoring.build_synthetic_technical_report([{"close": 100.0}]) is None


def test_build_synthetic_technical_report_uptrend_produces_matching_evidence():
    report = trade_scoring.build_synthetic_technical_report(_realistic_uptrend_history())
    assert report is not None
    assert report.department == trade_scoring.SYNTHETIC_TECHNICAL_DEPARTMENT
    evidence_blob = " ".join(report.evidence).lower()
    assert "uptrend" in evidence_blob


def test_build_synthetic_technical_report_downtrend_produces_matching_evidence():
    report = trade_scoring.build_synthetic_technical_report(_realistic_downtrend_history())
    assert report is not None
    evidence_blob = " ".join(report.evidence).lower()
    assert "downtrend" in evidence_blob


def test_build_synthetic_technical_report_feeds_entry_confirmation_correctly():
    """
    Direct proof that the synthetic report's evidence text genuinely
    drives build_entry_confirmation's checks — trend_alignment should be
    True for a real uptrend, and the overall confirmation shouldn't be
    stuck in the 'no usable technical report' fallback path.
    """
    report = trade_scoring.build_synthetic_technical_report(_realistic_uptrend_history())
    ec = trade_scoring.build_entry_confirmation(report, fundamental_score_value=75.0, risk_score_value=70.0)
    assert ec.trend_alignment is True
    assert "No usable technical report" not in " ".join(ec.notes)


def test_build_synthetic_technical_report_confidence_scales_with_available_indicators():
    report = trade_scoring.build_synthetic_technical_report(_realistic_uptrend_history())
    assert report.confidence == 90.0  # 30 base + 20*3, all three indicators available with 60 days of history


def test_risk_score_uses_worst_risk_level_and_penalizes_extra_flags():
    reports = [
        _report("Chief Asset Risk Officer", 0, risk_level=RiskLevel.ELEVATED, risks=["ATR expansion", "Weekend gap risk elevated"]),
    ]
    score, contributing, excluded = trade_scoring.risk_score(reports)
    # base 45 (ELEVATED) - 5 (one extra flag beyond the first) = 40
    assert score == 40.0
    assert contributing == ["Chief Asset Risk Officer"]


def test_risk_score_includes_chief_risk_fundamentals_officer():
    """
    Regression test: RISK_DEPARTMENTS was originally built before Chief
    Risk Fundamentals Officer existed and silently excluded it even when
    present in the reports passed to decide() — meaning its real,
    computed volatility/drawdown data was invisible to this engine's Risk
    Score entirely.
    """
    reports = [
        _report("Chief Risk Fundamentals Officer", 0, risk_level=RiskLevel.HIGH, risks=["Annualized Volatility is elevated"]),
    ]
    score, contributing, excluded = trade_scoring.risk_score(reports)
    assert "Chief Risk Fundamentals Officer" in contributing
    assert score == 20.0  # base 20 (HIGH), no extra-flag penalty (only one flag)


def test_risk_score_high_risk_floors_correctly_with_many_flags():
    reports = [
        _report("Chief Asset Risk Officer", 0, risk_level=RiskLevel.HIGH, risks=["a", "b", "c", "d", "e", "f", "g"]),
    ]
    score, _, _ = trade_scoring.risk_score(reports)
    assert score >= 0.0  # never negative
    assert score == max(0.0, 20.0 - 6 * 5.0)


def test_overall_score_is_weighted_blend():
    assert trade_scoring.overall_score(80, 60, 100) == round(80 * 0.4 + 60 * 0.4 + 100 * 0.2, 1)


def test_entry_confirmation_all_fail_without_technical_report():
    ec = trade_scoring.build_entry_confirmation(None, fundamental_score_value=80, risk_score_value=70)
    assert not ec.trend_alignment
    assert not ec.market_structure_confirmed
    assert ec.risk_acceptable  # risk was fine even without a technical report


def test_entry_confirmation_passes_when_trend_and_momentum_agree():
    tech = _report(
        "Chief Technical Officer", 40, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        evidence=["MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )
    ec = trade_scoring.build_entry_confirmation(tech, fundamental_score_value=70, risk_score_value=70)
    assert ec.trend_alignment
    assert ec.market_structure_confirmed
    assert ec.all_passed()


def test_entry_confirmation_volume_defaults_to_the_structure_proxy_without_volume_data():
    """Backward compatibility: when volumes_newest_first isn't passed at
    all, volume_confirmed must still mirror market_structure_confirmed
    exactly as before this fix — no behavior change for any existing
    caller that hasn't started passing real volume data."""
    tech = _report(
        "Chief Technical Officer", 40, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        evidence=["MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )
    ec = trade_scoring.build_entry_confirmation(tech, fundamental_score_value=70, risk_score_value=70)
    assert ec.volume_confirmed == ec.market_structure_confirmed


def test_entry_confirmation_volume_is_genuinely_independent_with_real_volume_data():
    """
    THE core regression test for a real finding from live dashboard
    review: market_structure_confirmed, breakout_confirmed, and
    volume_confirmed were all driven by the exact same underlying value,
    presenting as three independent confirmations when they were really
    one signal shown three times. With real volume data now available,
    volume_confirmed must be able to FAIL even when market_structure_confirmed
    PASSES (below-average recent volume, genuine uptrend) — proving the
    two are now genuinely decoupled, not still secretly identical.
    """
    tech = _report(
        "Chief Technical Officer", 40, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        evidence=["MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )
    low_volumes_newest_first = [400_000.0] * 5 + [1_000_000.0] * 45  # recent 5 days well below the 50-day baseline
    ec = trade_scoring.build_entry_confirmation(
        tech, fundamental_score_value=70, risk_score_value=70, volumes_newest_first=low_volumes_newest_first,
    )
    assert ec.market_structure_confirmed is True   # structure/momentum still agrees
    assert ec.volume_confirmed is False             # but real volume does NOT confirm this move
    assert not ec.all_passed()


def test_entry_confirmation_volume_confirmed_true_with_elevated_real_volume():
    tech = _report(
        "Chief Technical Officer", 40, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        evidence=["MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )
    elevated_volumes_newest_first = [2_000_000.0] * 5 + [1_000_000.0] * 45
    ec = trade_scoring.build_entry_confirmation(
        tech, fundamental_score_value=70, risk_score_value=70, volumes_newest_first=elevated_volumes_newest_first,
    )
    assert ec.volume_confirmed is True
    assert ec.all_passed()


def test_entry_confirmation_volume_falls_back_to_proxy_when_volume_data_unusable():
    """No usable volume (all zeros, e.g. an FX pair) must fall back to
    the same proxy as not passing volume at all — never silently treated
    as a failed check, which would unfairly penalize an asset class for a
    data source's own coverage gap (the same fairness principle already
    applied in agents/opportunity_screener.py)."""
    tech = _report(
        "Chief Technical Officer", 40, risk_level=RiskLevel.MODERATE,
        catalysts=["Price is in a sustained uptrend (20 SMA above 50 SMA)"],
        evidence=["MACD histogram is accelerating higher (+0.50)", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
    )
    unusable_volumes = [0.0] * 50
    ec = trade_scoring.build_entry_confirmation(
        tech, fundamental_score_value=70, risk_score_value=70, volumes_newest_first=unusable_volumes,
    )
    assert ec.volume_confirmed == ec.market_structure_confirmed  # falls back to the proxy, not penalized


def test_execution_rating_never_enters_on_weak_technical_confirmation():
    ec = trade_scoring.build_entry_confirmation(None, fundamental_score_value=90, risk_score_value=90)
    rating = trade_scoring.execution_rating(90, 90, 90, ec)
    assert rating != ExecutionRating.ENTER_NOW


def test_execution_rating_avoids_when_bias_too_weak():
    from models.trade_decision import EntryConfirmation
    ec = EntryConfirmation(
        trend_alignment=True, market_structure_confirmed=True,
        volume_confirmed=True, liquidity_confirmed=True, macro_alignment=True,
        risk_acceptable=True, minimum_rr_achieved=True,
    )
    rating = trade_scoring.execution_rating(51, 50, 90, ec)  # both scores near-neutral
    assert rating == ExecutionRating.AVOID


def test_trade_grade_caps_on_weakest_leg_not_average():
    # High overall score, but risk is terrible -> should NOT be top-tier
    grade = trade_scoring.trade_grade(overall_score_value=85, fundamental_score_value=90, technical_score_value=90, risk_score_value=15)
    assert grade.value in ("C", "D")
