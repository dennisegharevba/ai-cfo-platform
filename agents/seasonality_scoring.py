"""
Seasonality scoring.

Per the Institutional Fundamental Scoring Engine spec's "Seasonality" line
item (appearing under both Technical Context and Commodity Fundamentals,
and in the Final Investment Committee table at a supporting-only weight).

HONEST SCOPE — read before relying on this: the monthly scores below are
WELL-KNOWN, WIDELY-CITED seasonal tendencies from financial literature and
market commentary (e.g. gold's historical strength around Indian wedding
season and Chinese New Year demand, "sell in May" for US equities, winter
heating demand for natural gas, planting/harvest pressure for row crops).

They are NOT a statistical backtest this platform computed from historical
price data — this platform has no historical price database to run that
analysis against, and presenting a precise computed statistic without
having actually computed it would be a fabrication. What's here is a
documented, defensible set of DIRECTIONAL, MODERATE-MAGNITUDE scores
(capped well below +/-100, since seasonality is explicitly a supporting/
minor signal per the spec's own Final Investment Committee weighting, not
a primary driver) reflecting patterns widely discussed in market
commentary. Past seasonal tendencies are not a guarantee of future
performance — the standard, necessary caveat for any seasonality claim.

Only assets with an explicit entry in SEASONALITY_PATTERNS get a score;
every other asset returns None (no fabricated pattern for an asset this
module doesn't actually cover).
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Optional

# Asset display name -> {month (1-12): (score -100..+100, reasoning)}.
# Scores are deliberately moderate (rarely beyond +/-25) reflecting that
# this is a supporting signal, not a primary driver.
SEASONALITY_PATTERNS: Dict[str, Dict[int, tuple]] = {
    "Gold": {
        1: (10, "New Year investment buying carries over from year-end"),
        2: (-10, "Historically a seasonally weaker month for gold demand"),
        3: (-5, "Historically a seasonally weaker month for gold demand"),
        4: (0, "No strong seasonal pattern typically cited for this month"),
        5: (-10, "Historically a seasonally weaker month for gold demand"),
        6: (-5, "Historically a seasonally weaker month for gold demand"),
        7: (0, "No strong seasonal pattern typically cited for this month"),
        8: (15, "Pre-wedding-season buying historically begins to build"),
        9: (25, "Indian wedding season and festival (Diwali-period) buying historically a strong driver"),
        10: (20, "Festival buying historically continues into this month"),
        11: (15, "Chinese New Year restocking and Western holiday buying historically begin"),
        12: (10, "Year-end and Chinese New Year preparation buying historically continues"),
    },
    "WTI Crude Oil": {
        1: (0, "No strong seasonal pattern typically cited for this month"),
        2: (-10, "Spring refinery maintenance ('turnaround') historically reduces demand"),
        3: (-5, "Spring refinery maintenance historically continues"),
        4: (10, "US driving season demand historically begins building"),
        5: (15, "US driving season historically underway"),
        6: (20, "Peak US driving season demand historically supports prices"),
        7: (20, "Peak US driving season demand historically supports prices"),
        8: (15, "US driving season demand historically still elevated"),
        9: (-5, "Driving season ending and fall refinery maintenance historically begin"),
        10: (-10, "Fall refinery maintenance historically reduces demand"),
        11: (0, "No strong seasonal pattern typically cited for this month"),
        12: (0, "No strong seasonal pattern typically cited for this month"),
    },
    "Natural Gas": {
        1: (25, "Peak winter heating demand historically the strongest seasonal driver"),
        2: (20, "Winter heating demand historically still elevated"),
        3: (5, "Heating demand historically tapering as winter ends"),
        4: (-10, "Shoulder season historically sees the lowest demand"),
        5: (-15, "Shoulder season historically sees the lowest demand"),
        6: (-5, "Cooling demand historically begins to build"),
        7: (0, "Summer cooling demand historically a moderate driver"),
        8: (0, "Summer cooling demand historically a moderate driver"),
        9: (-10, "Shoulder season historically sees reduced demand"),
        10: (0, "Storage injection season historically wrapping up"),
        11: (15, "Winter heating season historically begins"),
        12: (20, "Winter heating demand historically ramping up"),
    },
    "Corn": {
        1: (0, "No strong seasonal pattern typically cited for this month"),
        2: (0, "No strong seasonal pattern typically cited for this month"),
        3: (5, "Pre-planting positioning historically begins"),
        4: (10, "Planting-season weather risk premium historically builds"),
        5: (15, "Planting-season weather risk premium historically peaks"),
        6: (10, "Growing-season weather risk (pollination approaching) historically a factor"),
        7: (5, "Pollination-period weather risk historically a factor for corn specifically"),
        8: (-5, "Crop conditions historically becoming clearer, reducing weather premium"),
        9: (-15, "Harvest pressure historically begins to build"),
        10: (-20, "Peak harvest pressure and increased supply historically weigh on prices"),
        11: (-10, "Harvest historically wrapping up"),
        12: (-5, "Post-harvest supply overhang historically continues"),
    },
    "Wheat": {
        1: (0, "No strong seasonal pattern typically cited for this month"),
        2: (0, "No strong seasonal pattern typically cited for this month"),
        3: (5, "Pre-planting/dormancy-break positioning historically begins"),
        4: (10, "Winter wheat crop-condition weather risk historically builds"),
        5: (15, "Winter wheat harvest approaches; weather risk premium historically peaks"),
        6: (5, "Winter wheat harvest historically begins, adding early supply"),
        7: (-10, "Winter wheat harvest pressure historically weighs on prices"),
        8: (-10, "Harvest supply overhang historically continues"),
        9: (0, "Winter wheat planting for the next cycle historically begins"),
        10: (0, "No strong seasonal pattern typically cited for this month"),
        11: (0, "No strong seasonal pattern typically cited for this month"),
        12: (0, "No strong seasonal pattern typically cited for this month"),
    },
    "Soybeans": {
        1: (0, "No strong seasonal pattern typically cited for this month"),
        2: (0, "No strong seasonal pattern typically cited for this month"),
        3: (5, "Pre-planting positioning historically begins"),
        4: (10, "Planting-season weather risk premium historically builds"),
        5: (15, "Planting-season weather risk premium historically peaks"),
        6: (10, "Growing-season weather risk historically a factor"),
        7: (10, "Pod-fill-period weather risk historically a factor for soybeans specifically"),
        8: (0, "Crop conditions historically becoming clearer"),
        9: (-15, "Harvest pressure historically begins to build"),
        10: (-20, "Peak harvest pressure and increased supply historically weigh on prices"),
        11: (-10, "Harvest historically wrapping up"),
        12: (-5, "Post-harvest supply overhang historically continues"),
    },
    "S&P500": {
        1: (10, "The historical 'January effect' is often cited as a modestly bullish seasonal pattern"),
        2: (0, "No strong seasonal pattern typically cited for this month"),
        3: (0, "No strong seasonal pattern typically cited for this month"),
        4: (10, "Historically one of the stronger calendar months for US equities"),
        5: (-10, "The 'sell in May and go away' seasonal pattern historically begins"),
        6: (-5, "Historically a softer summer month for US equities"),
        7: (0, "No strong seasonal pattern typically cited for this month"),
        8: (-5, "Historically a softer summer month for US equities"),
        9: (-15, "Historically cited as the weakest calendar month for US equities"),
        10: (0, "Historically volatile but has often marked seasonal lows"),
        11: (15, "Historically the start of the 'best six months' seasonal pattern"),
        12: (15, "The 'Santa Claus rally' and year-end positioning are widely cited bullish patterns"),
    },
    "NASDAQ100": {
        1: (10, "The historical 'January effect' is often cited as a modestly bullish seasonal pattern"),
        2: (0, "No strong seasonal pattern typically cited for this month"),
        3: (0, "No strong seasonal pattern typically cited for this month"),
        4: (10, "Historically one of the stronger calendar months for growth/tech equities"),
        5: (-10, "The 'sell in May and go away' seasonal pattern historically begins"),
        6: (-5, "Historically a softer summer month for growth/tech equities"),
        7: (0, "No strong seasonal pattern typically cited for this month"),
        8: (-5, "Historically a softer summer month for growth/tech equities"),
        9: (-15, "Historically cited as the weakest calendar month for US equities broadly"),
        10: (0, "Historically volatile but has often marked seasonal lows"),
        11: (15, "Historically the start of the 'best six months' seasonal pattern"),
        12: (15, "The 'Santa Claus rally' and year-end positioning are widely cited bullish patterns"),
    },
}

# Modest, fixed confidence for a documented-pattern (not live-measured)
# signal — deliberately lower than the 75.0 used for live FRED/EIA data,
# reflecting genuine epistemic uncertainty about how reliably a
# widely-cited historical pattern repeats in any given year.
SEASONALITY_CONFIDENCE = 45.0

# Low importance weight (1-10 scale) — seasonality is a supporting/minor
# signal per the spec's own Final Investment Committee weighting, not a
# primary driver.
SEASONALITY_IMPORTANCE_WEIGHT = 3.0


def score_seasonality(asset_or_theme: str, reference_date: date) -> Optional[tuple]:
    """
    Returns (score, reasoning_text) for `asset_or_theme` in the month of
    `reference_date`, or None if this asset has no configured seasonality
    pattern — never fabricates a pattern for an asset not in the table.
    """
    pattern = SEASONALITY_PATTERNS.get(asset_or_theme)
    if pattern is None:
        return None
    return pattern.get(reference_date.month)
