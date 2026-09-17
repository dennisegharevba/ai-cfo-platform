"""
Institutional Market Regime Filters.

Per an explicit upgrade request: Federal Reserve Policy, US 10-Year TIPS
Real Yield, US 10-Year Treasury Yield, and VIX must be evaluated alongside
Chief Macro Officer's existing factors and act as a HIGH-PRIORITY
CONFIRMATION LAYER — per the spec's own "Trade Filter Rule," this means
adjusting CONFIDENCE when the regime disagrees with the macro bias, never
overriding the macro bias's direction outright. This is the exact same
"confirmation, not override" philosophy already established by
agents/institutional_relationship.py's alignment classification (Full
Alignment/Mild Divergence/Strong Divergence adjusts confidence, never
bias) — reused here rather than inventing a second mechanism.

All four inputs are real, free, FRED-backed series — no new connector
needed, only three new series registrations (Fed Funds Rate, 10Y TIPS Real
Yield, VIX); the 10Y Treasury Yield and Dollar Index datasets are already
registered elsewhere in this platform (Chief Bond Strategist, Chief Macro
Officer respectively) and are REUSED here via the same DataIntegrityManager
keys, so this module causes zero duplicate fetching.

HONEST SCOPE — several spec line items have no free structured live
source and are handled as OPTIONAL, manually-suppliable overrides that
default to "not available" rather than being fabricated:
    - FOMC Statement text, Dot Plot, SEP, Powell press conference tone —
      pure text/qualitative analysis, would need NLP over Fed communications,
      not a numeric data feed. `fed_tone` accepts a manually-supplied
      classification (e.g. from a human reading the statement) and
      defaults to None (no adjustment) if not supplied.
    - CME FedWatch market-implied rate expectations — not a documented
      free API this platform integrates; `expected_decision` is likewise
      an optional manual input, defaulting to None (no surprise
      adjustment computed) rather than guessed.
The BASE Fed Policy score is computed from the ACTUAL, REAL Fed Funds Rate
trend — falling rates score bullish, rising score bearish — which is
genuine, live, and requires no manual input at all. The tone/surprise
overlays only activate if a caller actually supplies them.

Data source, updated 2026-09-17: this reads FRED's DFEDTARU (Federal Funds
Target Range — Upper Limit), a DAILY series, not FEDFUNDS (the monthly
average of the effective rate used here originally). The switch was made
after a same-day FOMC rate hike (2026-09-16) didn't show up anywhere on
this platform — FEDFUNDS's monthly-average publication schedule meant it
couldn't have, no matter how often the scheduled cycle ran. DFEDTARU
updates same-day/next-business-day per FRED's own metadata, so a policy
move is now visible on the very next scheduled cycle. Honest tradeoff
accepted by this choice: DFEDTARU is the upper limit of the target range,
not its midpoint — in practice the upper and lower limits move together
by the same increment at every FOMC decision, so this doesn't change
direction or magnitude of what gets scored, but it's worth naming plainly
rather than presenting "the Fed Funds Rate" as more precise than it is.

Internally, every component score uses this platform's standard -100..+100
scale (matching every other scoring function in the codebase) for full
consistency and reuse of bias_from_score()/FactorBias. `regime_score_to_display()`
converts the final combined score to the spec's own 0-100 display scale
with its exact 7-band labels, purely for presentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models.report import Bias, bias_from_score

# --- Fed Policy ---

# Point deltas applied on top of the Fed Funds Rate trend's base score,
# only when the caller supplies these OPTIONAL manual inputs (see module
# docstring — never fabricated, never guessed).
FED_SURPRISE_ADJUSTMENTS = {
    "none": 0.0,
    "small": 10.0,
    "large": 20.0,
    "major": 30.0,
}
FED_TONE_ADJUSTMENTS = {
    "very_dovish": 30.0,
    "dovish": 15.0,
    "neutral": 0.0,
    "hawkish": -15.0,
    "very_hawkish": -30.0,
}


def score_fed_policy(
    fed_funds_trend_score: Optional[float],
    fed_tone: Optional[str] = None,
    expected_decision: Optional[str] = None,
    actual_decision: Optional[str] = None,
    surprise_magnitude: Optional[str] = None,
) -> Optional[float]:
    """
    Base score (-100..+100) from the real Fed Funds Rate trend
    (falling = bullish, i.e. lower_is_bullish=True was already applied by
    the caller via agents.trend_scoring.series_trend_score). Optionally
    adjusted by a manually-supplied Fed tone classification
    ("very_dovish"/"dovish"/"neutral"/"hawkish"/"very_hawkish") and/or a
    manually-supplied surprise magnitude ("none"/"small"/"large"/"major"),
    signed by whether the actual decision was more dovish or hawkish than
    expected. Both overlays default to having no effect if not supplied.

    Returns None if fed_funds_trend_score itself is unavailable — no base
    signal, no score, consistent with every other factor in this platform.
    """
    if fed_funds_trend_score is None:
        return None

    score = fed_funds_trend_score

    if fed_tone is not None:
        score += FED_TONE_ADJUSTMENTS.get(fed_tone.lower().replace(" ", "_"), 0.0)

    if surprise_magnitude is not None and expected_decision is not None and actual_decision is not None:
        magnitude = FED_SURPRISE_ADJUSTMENTS.get(surprise_magnitude.lower(), 0.0)
        # A surprise CUT (vs an expected hold/hike) is bullish; a surprise
        # HIKE (vs an expected hold/cut) is bearish — sign the magnitude
        # by comparing the two decisions' relative hawkishness.
        _rank = {"cut": -1, "hold": 0, "hike": 1}
        expected_rank = _rank.get(expected_decision.lower(), 0)
        actual_rank = _rank.get(actual_decision.lower(), 0)
        if actual_rank < expected_rank:
            score += magnitude   # more dovish than expected
        elif actual_rank > expected_rank:
            score -= magnitude   # more hawkish than expected

    return max(-100.0, min(100.0, score))


# --- Real Yields (10Y TIPS) ---
# Point deltas exactly as specified, keyed by the monthly change magnitude
# in basis points. lower_is_bullish (falling real yields are bullish for
# Gold/growth stocks) — mirrors the same convention used across this codebase.
REAL_YIELD_STRONGLY_FALLING_BPS = 15.0   # >15bps fall over the trailing month
REAL_YIELD_MODERATELY_FALLING_BPS = 5.0
REAL_YIELD_MODERATELY_RISING_BPS = 5.0
REAL_YIELD_STRONGLY_RISING_BPS = 15.0


def score_real_yield(monthly_change_bps: Optional[float]) -> Optional[float]:
    """
    monthly_change_bps: the 10Y TIPS real yield's change over the trailing
    month, in basis points (positive = yield rose). Returns a -100..+100
    score using the spec's exact point bands, generalized onto this
    platform's standard scale (the spec's own +20/+10/-10/-20 deltas for
    Gold are used directly as the score, since they already sit within
    -100..100 and represent the same "how bullish/bearish" concept every
    other factor's score does).
    """
    if monthly_change_bps is None:
        return None

    if monthly_change_bps <= -REAL_YIELD_STRONGLY_FALLING_BPS:
        return 20.0
    if monthly_change_bps <= -REAL_YIELD_MODERATELY_FALLING_BPS:
        return 10.0
    if monthly_change_bps >= REAL_YIELD_STRONGLY_RISING_BPS:
        return -20.0
    if monthly_change_bps >= REAL_YIELD_MODERATELY_RISING_BPS:
        return -10.0
    return 0.0


# --- US 10-Year Treasury Yield ---
TREASURY_SHARP_RISE_BPS_PER_WEEK = 20.0


def score_treasury_yield(weekly_change_bps: Optional[float]) -> Optional[float]:
    """
    weekly_change_bps: the 10Y Treasury yield's change over the trailing
    week, in basis points. Falling yields are bullish (for Gold/growth
    stocks); a sharp rise (>20bps/week) is scored more severely per the
    spec's explicit "Sharp Rise" band.
    """
    if weekly_change_bps is None:
        return None

    if weekly_change_bps >= TREASURY_SHARP_RISE_BPS_PER_WEEK:
        return -15.0
    if weekly_change_bps > 2.0:
        return -8.0   # "Rising Yield" — bearish, not yet a sharp move
    if weekly_change_bps < -2.0:
        return 8.0    # "Falling Yield" — bullish
    return 0.0         # "Stable Yield" — neutral


# --- VIX ---
def score_vix(vix_level: Optional[float]) -> Optional[float]:
    """
    vix_level: the current VIX level. Returns a -100..+100 score using the
    spec's exact bands. VIX above 35 ("Extreme Risk-Off") scores maximally
    bearish AND should trigger the spec's explicit warning message — see
    vix_warning() below, kept separate so callers can surface it distinctly
    from the numeric score.
    """
    if vix_level is None:
        return None

    if vix_level < 15:
        return 20.0     # Risk-On
    if vix_level < 20:
        return 10.0     # Mild Bullish
    if vix_level < 25:
        return 0.0      # Neutral
    if vix_level < 30:
        return -20.0    # Risk-Off Warning
    if vix_level < 35:
        return -40.0    # High Risk
    return -100.0        # Extreme Risk-Off


def vix_warning(vix_level: Optional[float]) -> Optional[str]:
    """The spec's explicit warning message, only above the Extreme Risk-Off threshold."""
    if vix_level is not None and vix_level >= 35:
        return "Extreme volatility regime. Long equity setups should be avoided."
    return None


# --- Combined Institutional Market Regime Score ---
COMBINED_WEIGHTS = {
    "macro": 0.40,
    "fed_policy": 0.20,
    "real_yield": 0.15,
    "treasury_yield": 0.15,
    "vix": 0.10,
}


@dataclass
class InstitutionalMarketRegime:
    """The full regime read — every component plus the combined result."""

    macro_score: Optional[float] = None
    fed_policy_score: Optional[float] = None
    real_yield_score: Optional[float] = None
    treasury_yield_score: Optional[float] = None
    vix_score: Optional[float] = None
    combined_score: float = 0.0            # -100..+100 internal scale
    bias: Bias = Bias.NEUTRAL
    confidence: float = 0.0                # 0-100, based on how many components were available
    vix_warning_message: Optional[str] = None
    market_impact: Dict[str, str] = field(default_factory=dict)
    reasoning: str = ""

    def display_score(self) -> float:
        """Convert the internal -100..+100 combined_score to the spec's own 0-100 display scale."""
        return round((self.combined_score + 100.0) / 2.0, 1)

    def display_band(self) -> str:
        """The spec's exact 7-band label for the current display_score()."""
        score = self.display_score()
        if score >= 90:
            return "Strong Bullish"
        if score >= 75:
            return "Bullish"
        if score >= 60:
            return "Moderately Bullish"
        if score >= 45:
            return "Neutral"
        if score >= 30:
            return "Moderately Bearish"
        if score >= 15:
            return "Bearish"
        return "Strong Bearish"

    def to_dict(self) -> dict:
        return {
            "macro_score": self.macro_score,
            "fed_policy_score": self.fed_policy_score,
            "real_yield_score": self.real_yield_score,
            "treasury_yield_score": self.treasury_yield_score,
            "vix_score": self.vix_score,
            "combined_score": self.combined_score,
            "display_score": self.display_score(),
            "display_band": self.display_band(),
            "bias": self.bias.value,
            "confidence": self.confidence,
            "vix_warning_message": self.vix_warning_message,
            "market_impact": self.market_impact,
            "reasoning": self.reasoning,
        }


def combine_regime_scores(
    macro_score: Optional[float],
    fed_policy_score: Optional[float],
    real_yield_score: Optional[float],
    treasury_yield_score: Optional[float],
    vix_score: Optional[float],
    vix_level: Optional[float] = None,
) -> InstitutionalMarketRegime:
    """
    Combine every component using the spec's exact weights (Macro 40%,
    Fed Policy 20%, Real Yield 15%, Treasury Yield 15%, VIX 10%),
    RENORMALIZED over only the components that are actually available —
    a missing component contributes zero weight rather than being treated
    as neutral, matching this platform's standing "confidence reflects
    real data availability" rule.
    """
    components = {
        "macro": macro_score, "fed_policy": fed_policy_score,
        "real_yield": real_yield_score, "treasury_yield": treasury_yield_score,
        "vix": vix_score,
    }
    available = {k: v for k, v in components.items() if v is not None}

    if not available:
        return InstitutionalMarketRegime(
            macro_score=macro_score, fed_policy_score=fed_policy_score,
            real_yield_score=real_yield_score, treasury_yield_score=treasury_yield_score,
            vix_score=vix_score, combined_score=0.0, bias=Bias.NEUTRAL, confidence=0.0,
            vix_warning_message=vix_warning(vix_level),
        )

    total_weight = sum(COMBINED_WEIGHTS[k] for k in available)
    combined = sum(available[k] * COMBINED_WEIGHTS[k] for k in available) / total_weight
    combined = max(-100.0, min(100.0, combined))

    # Confidence scales with how much of the intended weight was actually
    # covered by real data — full coverage doesn't guarantee 100 confidence
    # (that's for the caller's own overall confidence calc), but partial
    # coverage should never present as fully confident.
    coverage_confidence = round(total_weight * 100.0, 1)

    return InstitutionalMarketRegime(
        macro_score=macro_score, fed_policy_score=fed_policy_score,
        real_yield_score=real_yield_score, treasury_yield_score=treasury_yield_score,
        vix_score=vix_score, combined_score=round(combined, 1),
        bias=bias_from_score(combined), confidence=coverage_confidence,
        vix_warning_message=vix_warning(vix_level),
    )


# --- Market impact table ---
def build_market_impact(
    fed_policy_score: Optional[float], real_yield_score: Optional[float], treasury_yield_score: Optional[float],
) -> Dict[str, str]:
    """
    Per the spec's FED MARKET IMPACT table: derive a simple Bullish/
    Neutral/Bearish label for each named asset from the available
    component directions. Each asset's label is driven primarily by
    whichever components most directly affect it, per the spec's own
    per-asset reasoning (Gold/Silver track Fed+real yields+Treasury
    yields; NASDAQ100/S&P500 track the same plus are more rate-sensitive;
    US Dollar and Treasury Bonds move opposite to the "risk assets" reading).
    """
    def _label(score: Optional[float]) -> str:
        if score is None:
            return "Neutral"
        if score > 10:
            return "Bullish"
        if score < -10:
            return "Bearish"
        return "Neutral"

    # Simple average across whichever rate-sensitive components are available.
    rate_components = [s for s in (fed_policy_score, real_yield_score, treasury_yield_score) if s is not None]
    rate_avg = sum(rate_components) / len(rate_components) if rate_components else None

    gold_silver_label = _label(rate_avg)
    equity_label = _label(rate_avg)
    # US Dollar and Treasury Bonds move opposite to the easing/tightening
    # direction that's bullish for Gold/equities (easing -> USD bearish;
    # tightening -> USD bullish); Treasury Bonds are bullish when yields fall.
    usd_label = _label(-rate_avg) if rate_avg is not None else "Neutral"
    bonds_label = _label(rate_avg)  # falling yields (bullish rate_avg) -> bond prices up

    return {
        "Gold": gold_silver_label,
        "Silver": gold_silver_label,
        "NASDAQ100": equity_label,
        "S&P500": equity_label,
        "US Dollar": usd_label,
        "Treasury Bonds": bonds_label,
    }


# --- Reasoning (deterministic templating, no LLM) ---
def build_regime_reasoning(regime: InstitutionalMarketRegime) -> str:
    """
    A short, deterministic paragraph covering the spec's explicit
    reasoning checklist — built entirely from template strings over
    already-computed values, consistent with every other narrative field
    in this platform (Chief Strategy Officer's trade_thesis, the
    Institutional Relationship Engine's commentary).
    """
    parts: List[str] = []

    if regime.macro_score is not None:
        direction = "supportive" if regime.macro_score > 0 else "a headwind" if regime.macro_score < 0 else "neutral"
        parts.append(f"The Macro report is {direction} for this bias.")

    if regime.fed_policy_score is not None:
        stance = "supportive (easing bias)" if regime.fed_policy_score > 0 else "restrictive (tightening bias)" if regime.fed_policy_score < 0 else "neutral"
        parts.append(f"Federal Reserve policy reads as {stance}.")

    if regime.real_yield_score is not None:
        direction = "supporting precious metals and growth stocks" if regime.real_yield_score > 0 else "hurting precious metals and growth stocks" if regime.real_yield_score < 0 else "not a meaningful factor right now"
        parts.append(f"Real yields are {direction}.")

    if regime.treasury_yield_score is not None:
        direction = "a tailwind" if regime.treasury_yield_score > 0 else "a headwind" if regime.treasury_yield_score < 0 else "roughly neutral"
        parts.append(f"Treasury yields are {direction}.")

    if regime.vix_score is not None:
        risk_stance = "Risk-On" if regime.vix_score > 0 else "Risk-Off" if regime.vix_score < 0 else "neutral"
        parts.append(f"VIX indicates a {risk_stance} regime.")
    if regime.vix_warning_message:
        parts.append(regime.vix_warning_message)

    if not parts:
        return "Insufficient data to form an institutional regime reasoning this cycle."

    if regime.bias == Bias.NEUTRAL:
        parts.append("Institutional positioning currently favors waiting for clearer confirmation.")
    elif regime.bias in (Bias.BULLISH, Bias.STRONGLY_BULLISH):
        parts.append("Institutional positioning currently favors buying.")
    else:
        parts.append("Institutional positioning currently favors selling or standing aside.")

    return " ".join(parts)
