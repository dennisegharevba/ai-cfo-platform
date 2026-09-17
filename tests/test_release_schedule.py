from datetime import datetime, timezone

from agents.release_schedule import (
    most_recent_cot_release_datetime, next_cot_release_datetime, is_new_cot_release_available,
)


def test_most_recent_release_from_a_sunday_is_the_prior_friday():
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)  # a Sunday
    recent = most_recent_cot_release_datetime(now)
    assert recent.date().isoformat() == "2026-08-28"  # the Friday before
    assert recent.hour == 15 and recent.minute == 30


def test_most_recent_release_at_the_exact_release_moment_is_that_moment():
    exact = datetime(2026, 8, 28, 19, 30, tzinfo=timezone.utc)  # 3:30pm EDT
    recent = most_recent_cot_release_datetime(exact)
    assert recent == exact.astimezone(recent.tzinfo)


def test_most_recent_release_one_minute_before_is_the_prior_week():
    just_before = datetime(2026, 8, 28, 19, 29, tzinfo=timezone.utc)
    recent = most_recent_cot_release_datetime(just_before)
    assert recent.date().isoformat() == "2026-08-21"  # a full week earlier


def test_handles_est_correctly_in_winter_no_daylight_saving():
    winter = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # a Thursday in January
    recent = most_recent_cot_release_datetime(winter)
    assert recent.date().isoformat() == "2026-01-09"
    assert recent.utcoffset().total_seconds() == -5 * 3600  # EST, not EDT


def test_handles_edt_correctly_in_summer_daylight_saving():
    summer = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    recent = most_recent_cot_release_datetime(summer)
    assert recent.utcoffset().total_seconds() == -4 * 3600  # EDT, not EST


def test_next_release_after_a_sunday_is_the_upcoming_friday():
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    nxt = next_cot_release_datetime(now)
    assert nxt.date().isoformat() == "2026-09-04"


def test_new_release_detected_across_a_friday_boundary():
    last_fetch = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)  # Monday, before that week's Friday release
    check_now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)   # the following Monday
    assert is_new_cot_release_available(last_fetch, check_now) is True


def test_no_new_release_detected_within_the_same_week():
    last_fetch = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)  # just after Friday's release
    check_now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)   # the next day, Saturday
    assert is_new_cot_release_available(last_fetch, check_now) is False


def test_naive_datetimes_are_handled_without_crashing():
    """This platform's convention elsewhere (core/refresh_manager.py) uses
    datetime.now(timezone.utc) — but a naive datetime must degrade
    gracefully (assumed UTC), not crash, for robustness against any
    caller that doesn't attach a timezone."""
    naive_now = datetime(2026, 8, 30, 12, 0)
    result = next_cot_release_datetime(naive_now)
    assert result.date().isoformat() == "2026-09-04"


def test_naive_last_fetched_at_handled_without_crashing():
    naive_last_fetch = datetime(2026, 8, 24, 12, 0)
    check_now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    assert is_new_cot_release_available(naive_last_fetch, check_now) is True
