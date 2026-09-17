# Dashboard Redesign — "Institutional Research Terminal" visual identity

## Design brief and direction

Given creative latitude ("you can redesign it") rather than a literal
mockup to match, the design process followed was: name the subject, its
audience, and the page's single job; propose a token system (color,
type, layout, signature); check it against the generic AI-design defaults
before building; only then implement.

**Subject**: an institutional multi-asset research terminal (macro,
commodities, equities, crypto, sentiment, seasonality, risk), used by one
technical, financially sophisticated researcher monitoring positioning
bias across many assets. **Single job of the redesigned Home page**: at a
glance, show what's actually been analyzed this session and its overall
read, with a path to drill into any category.

## Why dark + a single accent, here, is a choice and not a default

The generic AI-design cliché this could have fallen into is "a near-black
background with a single bright accent, applied regardless of subject."
The reason this wasn't that: dark backgrounds with a disciplined,
functional color system are the GENUINE visual vernacular of real trading
terminals (Bloomberg, TradingView) for a real, non-decorative reason —
reduced eye strain during extended data monitoring. The brief's own
subject matter justifies the direction; it wasn't picked by default.

The accent color, however, was deliberately NOT the generic AI-cliché
terracotta/vermilion (~#D97757, which reads as a tell on any brief). It's
`#C9A227` — an antique gold — chosen because THIS platform's own defining,
differentiating feature (built across the last several deliveries) is
precious-metals fundamentals: Gold, Silver, Platinum, and Palladium
fundamentally backed by real US Dollar data. The platform's visual
identity echoes its own actual subject matter rather than an
interchangeable brand color.

**Full token system** (`.streamlit/config.toml`, `dashboard/dashboard_utils.py`'s
`PLATFORM_COLORS`):
- Background: `#0B0E14` (cool near-black, not harsh pure black)
- Panel: `#131722`
- Accent (signature): `#C9A227` (antique gold)
- Bullish: `#3FB950` / Bearish: `#F85149` (controlled, not neon —
  and STRICTLY reserved for actual bullish/bearish signal, never
  decoration, matching how this platform already treats color-coding
  everywhere else)
- Text: `#E6E8EB` (soft white) / muted: `#7D8590`
- Type: a monospace treatment (`JetBrains Mono`/`IBM Plex Mono` stack)
  specifically for numeric metric values — numbers read as data, distinct
  from prose labels, itself a real structural signal for a terminal
  interface rather than decoration (`inject_terminal_css()`)

## The signature element: the bias gauge

Per the design process's own instruction to find "the single unique
element this page will be remembered by that embodies the brief" —
`render_bias_gauge()` is a horizontal -100..+100 gauge, color-graded from
bearish red through neutral gray to bullish green, with a marker at the
current score. This was chosen specifically because **bias_score on this
exact -100..+100 scale is the one value every single agent in this entire
platform produces** — Macro, Commodity Fundamentals, COT, Sentiment,
Seasonality, Risk, and the overall Strategy Officer synthesis all share
it. The signature visual is drawn directly from the platform's real,
actual data model, not a decorative addition invented for the redesign.

It now appears on the Department Reports card renderer, the Strategy
Synthesis page, and the redesigned Home page's Market Overview — the same
component, the same rendering, everywhere `bias_score` appears.

## A real bug caught and fixed before shipping

The gauge's first draft used `id(bias_score)` — Python object identity —
to generate each SVG gradient's unique `id` attribute. This is fragile:
`id()` is not a stable unique value, and when the same `bias_score` value
is passed to the function more than once (a routine case — a whole grid
of asset cards could easily include two departments with an identical
score), the resulting gradient IDs could collide, silently breaking the
gauge's gradient rendering for one of them. Fixed with a proper
`uuid.uuid4()`-based ID, and a dedicated regression test
(`test_render_bias_gauge_produces_unique_gradient_ids_across_calls`)
proves two calls with the IDENTICAL `bias_score` input still produce
different, unique gradient IDs.

## Home page: from a static description to a live "Market Overview"

The redesigned `dashboard/Home.py` no longer just describes what the
other pages do — it surfaces whatever's ACTUALLY been analyzed this
session: the latest Strategy Synthesis (if run) front and center with its
gauge, and every Department Report grouped by asset (so multiple
departments' reads on the same name appear together, the way a real
research desk would review one asset — not as an arbitrary flat list).
The "what's in this dashboard" explanation is still there, just moved into
a collapsed expander rather than being the page's main content.

Verified directly with a dedicated test (not assumed to work from the
existing empty-state test) — `test_home_market_overview_populated_state_does_not_crash`
populates real session-state reports and a real strategy report, then
confirms the grouped-card layout and gauges actually render.

## Testing

- 2 new tests specifically for the redesign's new render paths (the
  populated Market Overview state, and the gauge's gradient-ID
  uniqueness — the latter a genuine regression test for a bug caught
  before it shipped)
- Every existing dashboard test re-run and passing unchanged — the
  redesign is additive to every page's existing logic (theme + CSS +
  gauge component), not a rewrite of any page's underlying functionality
- 478 tests total, all passing

## What's not attempted

- An exact pixel-for-pixel recreation of the original spec's ASCII
  Market Overview / Final Investment Committee mockup — the redesign
  took the mockup's INTENT (an at-a-glance overview, grouped department
  detail, a clear bias readout) and expressed it through this platform's
  own visual identity and existing page structure, rather than rebuilding
  every page's layout from scratch to match specific ASCII box positions
- A literal "Final Investment Committee" table page — the same
  information (contributing departments, weights, confidence) already
  exists in `StrategyReport.decision_explanation` and the Department
  Reports factor tables; a dedicated table view is a natural, small,
  separately-scoped follow-up if wanted
