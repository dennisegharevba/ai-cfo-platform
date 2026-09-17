"""
Real, plain-English narrative generation for FundamentalFactor lines.

Update, 2026-09-17: a direct, explicit user complaint — the platform's
Fundamental Score page showed catalysts/risks like "Core CPI is supportive
(score +12.3)" with no actual number, no comparison to the prior reading,
and no explanation of why that matters. That's because every department
that builds an Institutional Fundamental Scoring Engine report (Chief
Macro Officer, Chief Commodity Fundamentals Officer) was turning each
FundamentalFactor into a catalyst/risk line via this exact template:

    f"{f.name} is supportive (score {f.score:+.1f})"

That threw away everything the factor actually knows about itself
(current_value, previous_value, the real change between them) and
substituted a bare score label. The data was never fake — the NARRATIVE
was just never built. This module is the fix: one shared, deterministic
(no LLM call, no new dependency) sentence-builder that every fundamental
department can use, fed by real current_value/previous_value data plus a
short, honest "why this matters" phrase authored per factor by whichever
department owns it (see each department's own *_NARRATIVE_META dict).

Deliberately NOT an LLM-generated summary (a later, larger option this
platform could still add) — this is the "smarter hand-built template"
half of that tradeoff: fully deterministic and auditable, at the cost of
needing real wording authored for each factor rather than an LLM
adapting phrasing on its own. See docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md.
"""

from __future__ import annotations

from models.fundamental_factor import FundamentalFactor

# Per-unit formatting. Values are printed exactly as the source data
# reports them (FRED/EIA units) — never rescaled or reinterpreted, so
# what's shown always matches what was actually fetched.
_UNIT_FORMATTERS = {
    "%": lambda v: f"{v:,.1f}%",
    "index": lambda v: f"{v:,.1f}",
    "$B": lambda v: f"${v:,.0f}B",
    "$M": lambda v: f"${v:,.0f}M",
    "K": lambda v: f"{v:,.0f}K",
    "Bcf": lambda v: f"{v:,.0f} Bcf",
    "$/hr": lambda v: f"${v:,.2f}/hr",
}


def format_value(value, unit: str) -> str:
    """Format one factor value with its real reporting unit. 'n/a' for a
    missing value — never fabricated, matching this codebase's existing
    convention (see agents/chief_macro_officer.py's _build_factor)."""
    if value is None:
        return "n/a"
    formatter = _UNIT_FORMATTERS.get(unit)
    if formatter is None:
        return f"{value:,.2f}"
    return formatter(value)


def describe_factor(
    factor: FundamentalFactor,
    unit: str = "",
    bullish_meaning: str = "",
    bearish_meaning: str = "",
    include_date: bool = True,
) -> str:
    """
    Build one real sentence for a FundamentalFactor — e.g.:

        "Core CPI (YoY): 3.2% (+0.2 vs. prior reading) — underlying
        inflation is running hot, a headwind against near-term rate cuts
        (as of 2026-09-10)"

    instead of the old "Core CPI (YoY) is a headwind (score -14.2)".
    `bullish_meaning`/`bearish_meaning` are short, factor-specific
    plain-English explanations of why that direction matters — shown only
    when they match the factor's actual computed bias, so a neutral
    factor gets the number with no meaning clause tacked onto it (nothing
    fabricated for a reading that isn't actually bullish or bearish).
    """
    current = format_value(factor.current_value, unit)
    change = factor.change_from_previous
    if change is not None:
        sign = "+" if change >= 0 else ""
        trend = f" ({sign}{change:,.1f} vs. prior reading)"
    else:
        trend = ""

    meaning = ""
    if factor.bias.value == "bullish" and bullish_meaning:
        meaning = f" — {bullish_meaning}"
    elif factor.bias.value == "bearish" and bearish_meaning:
        meaning = f" — {bearish_meaning}"

    date_note = ""
    if include_date and factor.last_updated is not None:
        date_note = f" (as of {factor.last_updated.date()})"

    return f"{factor.name}: {current}{trend}{meaning}{date_note}"
