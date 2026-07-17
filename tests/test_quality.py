from datetime import datetime, timedelta, timezone

from core.quality import score_quality


def test_perfect_fresh_primary_valid_scores_100():
    now = datetime.now(timezone.utc)
    score = score_quality(
        time_collected=now, ttl_seconds=300, is_backup_source=False, shape_valid=True, now=now,
    )
    assert score == 100.0


def test_half_expired_ttl_reduces_freshness_component():
    now = datetime.now(timezone.utc)
    collected = now - timedelta(seconds=150)
    score = score_quality(
        time_collected=collected, ttl_seconds=300, is_backup_source=False, shape_valid=True, now=now,
    )
    # freshness ~50 * 0.5 = 25, source 100*0.3=30, shape 100*0.2=20 => 75
    assert 74.0 <= score <= 76.0


def test_backup_source_scores_lower_than_primary():
    now = datetime.now(timezone.utc)
    primary_score = score_quality(
        time_collected=now, ttl_seconds=300, is_backup_source=False, shape_valid=True, now=now,
    )
    backup_score = score_quality(
        time_collected=now, ttl_seconds=300, is_backup_source=True, shape_valid=True, now=now,
    )
    assert backup_score < primary_score


def test_failed_shape_validation_drags_score_down():
    now = datetime.now(timezone.utc)
    score = score_quality(
        time_collected=now, ttl_seconds=300, is_backup_source=False, shape_valid=False, now=now,
    )
    assert score == 80.0  # freshness(50) + source(30) but shape(0) => 80


def test_expired_data_has_zero_freshness_component():
    now = datetime.now(timezone.utc)
    collected = now - timedelta(seconds=1000)
    score = score_quality(
        time_collected=collected, ttl_seconds=300, is_backup_source=False, shape_valid=True, now=now,
    )
    assert score == 50.0  # source(30) + shape(20), freshness floored at 0
