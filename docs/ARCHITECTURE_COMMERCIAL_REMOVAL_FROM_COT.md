# Commercial Traders removed as a directional COT input

## What changed

Per an explicit later decision, Commercial Traders (hedgers) were removed
as a directional input to the Chief Commodity Analyst and Chief FX
Analyst entirely. Commercial positioning no longer influences bias,
confidence, or the overall market score anywhere in the platform's main
scoring pipeline. Primary emphasis is now on Non-Commercial Traders
(Large Speculators), on the reasoning that they're more representative of
trend-following institutional capital that drives medium- to long-term
price movements.

This is a genuine behavior change, not a relabeling: `PositioningAgent`
(`agents/positioning_agent_base.py`) previously blended speculative (60%)
and commercial (40%) net-position trend into `bias_score`, with an
alignment/divergence classification between them affecting confidence.
All of that blending and classification was removed. `bias_score` is now
100% driven by Non-Commercial net position trend alone.

## What replaced the commercial signal: deeper analysis of the speculative side

Rather than simply dropping 40% of the analysis, the upgrade adds real
depth to the Non-Commercial side via a new module,
`agents/speculative_positioning_analysis.py`:

- **`latest_weekly_change`** — the raw week-over-week change in
  Non-Commercial net position (contracts), distinct from the existing
  multi-week trend (`agents.positioning_scoring.net_position_trend_score`,
  unchanged and still reused, not duplicated). This answers "is
  positioning building, reducing, or unwinding *right now*," which a
  multi-week trend score alone doesn't capture.
- **`percentile_rank`** — where the current net position sits (0-100)
  relative to the fetched history window, flagging positioning extremes
  in the speculator base's own recent behavior. **Honest limitation**:
  this is a within-fetched-window percentile (typically 8 weeks, per
  `CotConnector`'s default), not a true multi-year historical percentile
  — the module's docstring says so explicitly. Widening it is a config
  change (`weeks_history=` on `CotConnector`), not a logic change.
- **`classify_momentum_signal`** — combines the multi-week trend with the
  latest weekly move into one of `"continuation"` (weekly move confirms
  the broader trend), `"reversal_watch"` (weekly move meaningfully
  opposes it — an early stall/reversal warning), `"stable"` (weekly move
  too small to read), or `"insufficient_data"`.

## The new confidence model (single-component, since Commercial is gone)

```
confidence = 55.0 (base, if a Non-Commercial trend is computable)
            + 15.0  if momentum_signal == "continuation"
            - 15.0  if momentum_signal == "reversal_watch"
            -  0.0  if momentum_signal == "stable"
            - 10.0  if positioning is at a percentile extreme (either direction)
clamped to 0-100
```

Every constant is a named module-level value
(`BASE_CONFIDENCE`, `MOMENTUM_CONTINUATION_BONUS`, etc. in
`positioning_agent_base.py`), not a magic number, per this codebase's
standing convention. Three worked examples are directly encoded as tests
in `tests/test_chief_commodity_and_fx_analysts.py` — continuation-only
(confidence 70), reversal-watch-only (confidence 40), and extreme-only
(confidence 45) — each isolating one signal from the others by
construction, with the exact arithmetic shown in the test's own comments.

## Risk flagging: two independent "crowding" concepts, now clearly distinguished

- **`positioning_extremity_flag`** (unchanged) — net position as a
  percent of total open interest: crowding relative to the market's total
  size.
- **NEW**: percentile-extreme + `reversal_watch` together — crowding
  relative to the speculator base's OWN recent history, compounded with
  an active reversal signal. This escalates `risk_level` to `ELEVATED`
  (via the shared `worse_risk_level` helper) independently of the first flag.

Both can fire simultaneously (a position can be large relative to the
market AND at a fresh extreme relative to its own recent history) — the
report can show both risk lines.

## The Chief Strategy Officer now weights COT well below fundamentals

Per the explicit directive that "Non-Commercial positioning [is used] only
as a supporting confirmation rather than the primary reason for a trade,"
`DEFAULT_DEPARTMENT_WEIGHTS` in `agents/chief_strategy_officer.py` now
includes:

```python
"Chief Commodity Analyst": 0.4,
"Chief FX Analyst": 0.4,
```

against the fundamental desks' (Macro, Bond, Equity, Crypto) default of
1.0. This isn't just documentation — `tests/test_chief_strategy_officer.py`
proves it changes actual outcomes: a scenario is constructed where a
confident-but-opposing fundamental read and a more-confident COT read are
pitted against each other, with the numbers worked out by hand in the
test's comments showing that EQUAL weighting would produce a bullish
synthesis (+20.6) while the actual 0.4-weighted COT produces a bearish one
(-1.9) — the de-weighting genuinely flips which side wins, not just
softens the COT side's pull.

## Commercial data can still be DISPLAYED — but never scored — via a config flag

Per the directive "unless they are explicitly enabled through a future
configuration option," a new setting was added:
`config.settings.ENABLE_COMMERCIAL_POSITIONING_DISPLAY` (env var
`ENABLE_COMMERCIAL_POSITIONING_DISPLAY`, defaults to `false`).

**Critically**: even when enabled, Commercial data is computed
independently and only ever appended as an evidence line explicitly
labeled `"[Informational only, not used in scoring]"` — it is NEVER folded
into `bias_score` or `confidence`, regardless of the flag. This was a
deliberate reading of the spec: the "no influence on scores" directive has
no exception clause attached to it, while the "remove all references...
unless explicitly enabled" sentence is specifically about visibility, not
about restoring commercial's effect on scoring.
`tests/test_chief_commodity_and_fx_analysts.py::test_commercial_data_shown_when_enabled_but_never_affects_bias_or_confidence`
proves this directly: two runs with identical setup but deliberately
*opposite* commercial data, flag enabled, produce byte-identical
`bias_score` and `confidence` — only the informational evidence text differs.

## What was deliberately left untouched: the Trade Decision Engine

`agents/asset_risk_officer.py` (part of the separate Institutional Trade
Decision Engine) still computes a commercial-vs-speculative divergence
check for its own per-asset risk scoring, using the same generic
`agents/positioning_scoring.py` module (parameterized by `long_key`/
`short_key`, unchanged). This is a different feature (trade entry risk for
a position the user is actively considering) from the main research
pipeline (ongoing directional research on an asset), and was left alone —
consistent with the same scoping decision made when Chief Technical
Officer was removed (see `docs/ARCHITECTURE_TECHNICAL_OFFICER_REMOVAL.md`).
`agents/positioning_scoring.py` itself was NOT modified — it's a generic,
parameterized module with legitimate ongoing use elsewhere, so the
commercial-removal work only touched the code that CALLS it
(`positioning_agent_base.py`), not the shared module itself.

## What's now orphaned (not deleted): the Institutional Relationship Engine's alignment logic

`agents/institutional_relationship.py`'s `AlignmentStatus` /
`classify_alignment` / `apply_confidence_adjustment` / `describe_alignment`
were the mechanism that PREVIOUSLY classified commercial-vs-speculative
agreement. Since `PositioningAgent` no longer computes a commercial trend
at all (by default), there's nothing left for these functions to classify
— they're no longer called anywhere in the active pipeline. They were kept
(not deleted) since they're generic, independently tested logic that could
be reused for a different pair of signals later, but the module's
docstring was updated to say so plainly rather than leaving a
misleading impression that they're still part of the live scoring path.
`ExecutionReadiness` / `classify_execution_readiness` /
`build_institutional_commentary` in that same file remain active, used by
`agents/chief_strategy_officer.py`.

## Testing

- 17 new tests for `agents/speculative_positioning_analysis.py` (weekly
  change, percentile ranking including a tie-handling case, extreme
  classification, momentum signal classification, all edge cases)
- `tests/test_chief_commodity_and_fx_analysts.py` fully rewritten: the old
  commercial-blend tests were replaced with continuation/reversal/extreme
  scenarios (each with hand-verified arithmetic in comments) and two tests
  proving the informational-display flag's behavior (off by default, and
  — when on — provably non-scoring)
- 4 new tests in `tests/test_chief_strategy_officer.py` proving the new
  department weighting exists AND changes real synthesis outcomes
- 332 tests total, all passing; the existing demo scripts
  (`demo_commodity_fx_agents.py`, `demo_strategy_officer.py`) and
  `scripts/run_daily_cycle.py` were all re-run end-to-end to confirm
  nothing else broke. `demo_strategy_officer.py`'s illustrative example
  report was also updated — it previously hardcoded a stale
  "Institutional Divergence (commercials)..." example line that the real
  agent no longer produces by default, which would have been misleading
  to leave in place.
