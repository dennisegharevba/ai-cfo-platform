"""
Chief Seasonality Officer.

Architecturally distinct from BaseAgent-shaped agents (Chief Macro
Officer, Chief Commodity Fundamentals Officer, etc.): this agent fetches
NO data through the DataIntegrityManager at all — its only input is the
current calendar date and the asset name, matched against
agents.seasonality_scoring.SEASONALITY_PATTERNS. This mirrors the same
"pure computation, no data fetch" architectural shape already established
by ChiefStrategyOfficer and ChiefExecutionOfficer (see agents/__init__.py's
docstring) — a calendar lookup needs no DataIntegrityManager involvement,
and forcing one would be architectural padding, not genuine consistency.

See agents/seasonality_scoring.py's docstring for the honest scope caveat:
these are widely-cited historical market patterns, not a statistical
backtest this platform computed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from models.report import AgentReport, RiskLevel
from models.fundamental_factor import FundamentalFactor, factor_bias_from_score

from .fundamental_scoring_engine import score_category
from .seasonality_scoring import score_seasonality, SEASONALITY_CONFIDENCE, SEASONALITY_IMPORTANCE_WEIGHT

CATEGORY = "Seasonality"


class ChiefSeasonalityOfficer:
    department = "Chief Seasonality Officer"

    def __init__(self, reference_date: Optional[date] = None):
        """reference_date defaults to today — pass an explicit date for
        testing or for scoring a specific point in time."""
        self.reference_date = reference_date or date.today()

    def analyze(self, asset_or_theme: str) -> AgentReport:
        factors: List[FundamentalFactor] = []
        data_gaps: List[str] = []

        result = score_seasonality(asset_or_theme, self.reference_date)
        if result is None:
            data_gaps.append(f"No seasonality pattern configured for '{asset_or_theme}' yet")
        else:
            score, reasoning = result
            month_name = self.reference_date.strftime("%B")
            # last_updated reflects when THIS read was computed — there's
            # no fetched provider timestamp for a calendar lookup, but
            # "as of" still has a genuine, honest value: right now.
            computed_at = datetime.combine(self.reference_date, datetime.min.time(), tzinfo=timezone.utc)
            factors.append(FundamentalFactor(
                name=f"{month_name} Seasonality",
                category=CATEGORY,
                current_value=float(self.reference_date.month),
                previous_value=None,
                forecast_value=None,
                score=float(score),
                bias=factor_bias_from_score(score),
                importance_weight=SEASONALITY_IMPORTANCE_WEIGHT,
                confidence=SEASONALITY_CONFIDENCE,
                source="Documented historical market pattern (not live-measured)",
                last_updated=computed_at,
                notes=[reasoning],
            ))

        category_result = score_category(CATEGORY, factors)

        evidence = [f"{f.name}: {f.bias.value} (score {f.score:+.1f}) — {f.notes[0]}" for f in factors]
        catalysts = [f"{f.notes[0]}" for f in factors if f.bias.value == "bullish"]
        risks = [f"{f.notes[0]}" for f in factors if f.bias.value == "bearish"]

        return AgentReport(
            department=self.department,
            asset_or_theme=asset_or_theme,
            bias=category_result.bias,
            bias_score=category_result.category_score,
            confidence=category_result.category_confidence,
            risk_level=category_result.risk_level if factors else RiskLevel.HIGH,
            catalysts=catalysts,
            risks=risks,
            evidence=evidence,
            data_gaps=data_gaps,
            factor_breakdown=factors,
        )
