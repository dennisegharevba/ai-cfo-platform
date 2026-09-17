"""
Market regime classification and dynamic category weighting.

Per the upgrade spec's "Dynamic Weighting" requirement: category
importance should adjust based on market conditions (FOMC weeks get more
macro weight, earnings season gets more corporate-fundamental weight,
etc.) rather than using permanently fixed weights.

HONEST SCOPE NOTE: this is a deterministic, RULE-BASED regime classifier —
not a self-learning/backtested system. The spec's own language ("dynamically
adjust... depending on market conditions") could be read as asking for an
adaptive system that tunes itself from historical outcomes; that would need
a real backtesting harness against historical data, which is a substantial
project of its own (the same honest-scope call already made for
agents/institutional_relationship.py's confidence-adjustment constants —
see docs/ARCHITECTURE_INSTITUTIONAL_RELATIONSHIP_ENGINE.md). What's built
here instead is a small number of NAMED, EXPLAINABLE rules a person can
read and verify, each toggled by a genuinely determinable condition (a
real calendar date, not an inferred one) — consistent with this
platform's standing preference for auditable logic over black-box scoring.

FOMC meeting dates specifically: `config/fomc_meeting_dates.py` ships as a
small, EXPLICITLY user-maintained list (not fabricated from training data)
— see that file's own docstring for why, and where to get the real,
current schedule.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Set

# Earnings season: the four multi-week windows every year when the bulk of
# US corporate earnings are reported, by month — a commonly used
# approximation, not an exact per-company calendar.
EARNINGS_SEASON_MONTHS = {1, 4, 7, 10}

# How many days before/after an FOMC meeting date counts as "FOMC week" —
# markets typically start positioning ahead of the announcement and react
# for a day or two afterward.
FOMC_WINDOW_DAYS_BEFORE = 3
FOMC_WINDOW_DAYS_AFTER = 1


class MarketRegime(str, Enum):
    FOMC_WEEK = "fomc_week"
    EARNINGS_SEASON = "earnings_season"
    NORMAL = "normal"


def classify_regime(
    reference_date: date, fomc_meeting_dates: Optional[List[date]] = None,
) -> Set[MarketRegime]:
    """
    Returns the set of active regimes for `reference_date`. Can return
    multiple simultaneously (an FOMC decision can land during earnings
    season). Returns {MarketRegime.NORMAL} if nothing else applies.

    fomc_meeting_dates: pass config.fomc_meeting_dates.FOMC_MEETING_DATES
    (or your own list) — if empty/not supplied, FOMC_WEEK simply never
    triggers, which is the honest behavior when no real schedule has been
    configured (never fabricates a meeting date).
    """
    active: Set[MarketRegime] = set()

    if reference_date.month in EARNINGS_SEASON_MONTHS:
        active.add(MarketRegime.EARNINGS_SEASON)

    for meeting_date in (fomc_meeting_dates or []):
        days_diff = (reference_date - meeting_date).days
        if -FOMC_WINDOW_DAYS_BEFORE <= days_diff <= FOMC_WINDOW_DAYS_AFTER:
            active.add(MarketRegime.FOMC_WEEK)
            break

    if not active:
        active.add(MarketRegime.NORMAL)

    return active


# Multiplier applied to a category's base weight when a given regime is
# active. Categories not listed for a given regime are left unchanged
# (multiplier 1.0). Multiple active regimes multiply together.
REGIME_CATEGORY_MULTIPLIERS: Dict[MarketRegime, Dict[str, float]] = {
    MarketRegime.FOMC_WEEK: {
        "Macroeconomic": 1.4,
    },
    MarketRegime.EARNINGS_SEASON: {
        "Equity Fundamentals": 1.3,
    },
    MarketRegime.NORMAL: {},
}


def regime_adjusted_weight(base_weight: float, category: str, active_regimes: Set[MarketRegime]) -> float:
    """
    Apply every active regime's multiplier for `category` (1.0 — no
    change — if a regime doesn't mention that category), multiplicatively.
    """
    weight = base_weight
    for regime in active_regimes:
        multiplier = REGIME_CATEGORY_MULTIPLIERS.get(regime, {}).get(category, 1.0)
        weight *= multiplier
    return weight
