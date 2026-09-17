from agents.news_digest import build_weekly_sentiment_digest


def _report(bias, bias_score, confidence, catalysts, risks, recorded_at):
    return {
        "bias": bias, "bias_score": bias_score, "confidence": confidence,
        "catalysts": catalysts, "risks": risks, "recorded_at": recorded_at,
    }


def test_returns_none_for_empty_input():
    """Never a fabricated digest from zero reports — that would
    misleadingly imply a real, quiet week rather than 'no data available'."""
    assert build_weekly_sentiment_digest([]) is None


def test_report_count_matches_input():
    reports = [
        _report("bullish", 10.0, 60.0, [], [], "2026-08-30T10:00:00+00:00"),
        _report("neutral", 0.0, 50.0, [], [], "2026-08-29T10:00:00+00:00"),
    ]
    digest = build_weekly_sentiment_digest(reports)
    assert digest.report_count == 2


def test_date_range_spans_oldest_to_newest():
    """Input is newest-first (ReportStore's own ordering) — the digest
    must correctly identify the actual oldest and newest recorded_at,
    not just take the first/last positionally without regard to order."""
    reports = [
        _report("bullish", 10.0, 60.0, [], [], "2026-08-30T10:00:00+00:00"),  # newest
        _report("neutral", 0.0, 50.0, [], [], "2026-08-28T10:00:00+00:00"),
        _report("bearish", -5.0, 55.0, [], [], "2026-08-24T10:00:00+00:00"),  # oldest
    ]
    digest = build_weekly_sentiment_digest(reports)
    assert digest.date_range_start == "2026-08-24T10:00:00+00:00"
    assert digest.date_range_end == "2026-08-30T10:00:00+00:00"


def test_average_bias_score_and_confidence_computed_correctly():
    reports = [
        _report("bullish", 20.0, 80.0, [], [], "2026-08-30T10:00:00+00:00"),
        _report("bearish", -10.0, 60.0, [], [], "2026-08-29T10:00:00+00:00"),
    ]
    digest = build_weekly_sentiment_digest(reports)
    assert digest.average_bias_score == 5.0    # (20 + -10) / 2
    assert digest.average_confidence == 70.0   # (80 + 60) / 2


def test_bias_day_counts_tallied_correctly():
    reports = [
        _report("bullish", 10.0, 60.0, [], [], "2026-08-30T10:00:00+00:00"),
        _report("bullish", 15.0, 65.0, [], [], "2026-08-29T10:00:00+00:00"),
        _report("neutral", 0.0, 50.0, [], [], "2026-08-28T10:00:00+00:00"),
        _report("bearish", -5.0, 55.0, [], [], "2026-08-27T10:00:00+00:00"),
    ]
    digest = build_weekly_sentiment_digest(reports)
    assert digest.bias_day_counts == {"bullish": 2, "neutral": 1, "bearish": 1}


def test_top_catalysts_deduplicated_and_ranked_by_frequency():
    reports = [
        _report("bullish", 10.0, 60.0, ["Strong jobs data"], [], "2026-08-30T10:00:00+00:00"),
        _report("bullish", 15.0, 65.0, ["Strong jobs data"], [], "2026-08-29T10:00:00+00:00"),
        _report("neutral", 0.0, 50.0, ["Mixed earnings"], [], "2026-08-28T10:00:00+00:00"),
    ]
    digest = build_weekly_sentiment_digest(reports)
    assert digest.top_catalysts[0] == "Strong jobs data"  # appeared twice, ranked first
    assert digest.top_catalysts.count("Strong jobs data") == 1  # deduplicated, not repeated


def test_top_risks_respects_top_n():
    reports = [
        _report("bullish", 10.0, 60.0, [], [f"Risk {i}"], "2026-08-30T10:00:00+00:00")
        for i in range(10)
    ]
    digest = build_weekly_sentiment_digest(reports, top_n=3)
    assert len(digest.top_risks) == 3


def test_missing_catalysts_or_risks_keys_handled_gracefully():
    """A report dict missing catalysts/risks entirely (rather than an
    empty list) must not crash — degrades gracefully."""
    reports = [{"bias": "neutral", "bias_score": 0.0, "confidence": 50.0, "recorded_at": "2026-08-30T10:00:00+00:00"}]
    digest = build_weekly_sentiment_digest(reports)
    assert digest.top_catalysts == []
    assert digest.top_risks == []
