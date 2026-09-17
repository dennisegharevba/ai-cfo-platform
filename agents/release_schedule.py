"""
COT (Commitment of Traders) release schedule — the CFTC publishes real
COT data weekly, every Friday at 3:30pm Eastern Time, reflecting the
prior Tuesday's positioning.

Why this exists: config/refresh_intervals.py's own comment already
acknowledges the gap — "cot_report": ... # weekly, force-refresh on
publish day instead. The flat 7-day TTL currently in use just waits 7
days from whenever the LAST successful fetch happened, which drifts out
of alignment with the real, fixed weekly schedule over time (an early
fetch one week shifts every subsequent refresh earlier too). This module
answers "has a new COT report actually been published since I last
fetched" directly, against the real schedule, rather than a generic timer.

Uses zoneinfo (standard library) for America/New_York, so EST/EDT
transitions are handled correctly automatically — no hardcoded UTC
offset that would silently drift wrong twice a year.

Honest, accepted limitation: this does not account for US federal
holidays, which occasionally push the real CFTC release to the following
business day. Handling that correctly would require a maintained holiday
calendar; treated here as an accepted edge case, not silently pretended
away — a holiday-shifted week may show slightly stale data as "not yet
due for refresh" for one extra day.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")
_RELEASE_TIME = time(15, 30)  # 3:30pm ET
_RELEASE_WEEKDAY = 4  # Monday=0 ... Friday=4


def most_recent_cot_release_datetime(now: datetime) -> datetime:
    """
    The most recent Friday 3:30pm ET at or before `now`. `now` may be
    naive (assumed UTC, matching this platform's convention elsewhere —
    e.g. core/refresh_manager.py's datetime.now(timezone.utc)) or
    timezone-aware; either way, comparison happens in Eastern time.
    """
    if now.tzinfo is None:
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    now_et = now.astimezone(_EASTERN)

    days_since_friday = (now_et.weekday() - _RELEASE_WEEKDAY) % 7
    candidate_date = (now_et - timedelta(days=days_since_friday)).date()
    candidate = datetime.combine(candidate_date, _RELEASE_TIME, tzinfo=_EASTERN)

    if candidate > now_et:
        candidate -= timedelta(days=7)
    return candidate


def next_cot_release_datetime(after: datetime) -> datetime:
    """The next Friday 3:30pm ET strictly after `after`."""
    most_recent = most_recent_cot_release_datetime(after)
    return most_recent + timedelta(days=7)


def is_new_cot_release_available(last_fetched_at: datetime, now: datetime) -> bool:
    """
    True if a real COT release has happened since last_fetched_at — i.e.
    the most recent Friday-3:30pm-ET release, as of `now`, is later than
    when data was last actually fetched. This is what should trigger a
    force-refresh, replacing the flat 7-day TTL.
    """
    if last_fetched_at.tzinfo is None:
        from datetime import timezone
        last_fetched_at = last_fetched_at.replace(tzinfo=timezone.utc)
    return most_recent_cot_release_datetime(now) > last_fetched_at
