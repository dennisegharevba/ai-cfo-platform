# Architecture — Phase 9: Chief Execution Officer

## All 12 Chief Officers are now built

This is the twelfth and final department from the original spec. What's
left after this (Phase 10+) is presentation and automation — the
dashboard, and scheduled orchestration — not another analytical desk.

## Where this agent fits: gate, not analyst

`ChiefExecutionOfficer` fetches no data from `DataIntegrityManager` — like
the Chief Strategy Officer (Phase 7), its only input is something another
agent already produced: here, a `StrategyReport`. Its entire job is a
yes/no gate: given a synthesis that's already been computed, should a human
actually be pinged about it right now.

```
ChiefExecutionOfficer.process(strategy_report)
    |
    +-- evaluate(strategy_report) -> ExecutionDecision   (pure, no side effects)
    |       - confidence_score >= min_confidence?
    |       - bias non-neutral and |bias_score| >= min_bias_magnitude?
    |       - risk_level <= max_acceptable_risk?
    |       - excluded_departments fraction <= max_excluded_fraction?
    |
    +-- if should_alert AND an alerter is configured:
            format_alert_message() -> TelegramAlerter.send_message()
            (failure is recorded on the decision, never silently swallowed)
```

`evaluate()` is deliberately separable from `process()` — it's useful on
its own (e.g. for a dashboard to show "would this have alerted?" without
actually sending anything), and keeping it pure makes it trivial to test
every gating condition in isolation without touching the network.

## Mapping the spec's four conditions onto what Phase 7 already computed

The spec asks for alerts only when "Confidence exceeds a threshold, Macro
agrees, Fundamentals agree, Technical analysis confirms, Risk model
approves, and Required data is fresh and validated." Four of those six
phrases are really describing ONE thing from this platform's point of
view: cross-department agreement. The Chief Strategy Officer (Phase 7)
already resolved that into `overall_bias_score`/`confidence_score` via its
weighted-mean-and-disagreement-penalty math — re-deriving "do macro,
fundamentals, and technicals all agree" independently here would be
duplicating work Phase 7 already did honestly. So:

| Spec condition | How Phase 9 checks it |
|---|---|
| Confidence exceeds a threshold | `confidence_score >= min_confidence` (default 65) |
| Macro/fundamentals/technical agree | `bias` is non-neutral and `\|bias_score\|` clears `min_bias_magnitude` (default 15 — the same cutoff `bias_from_score` uses for its neutral band) |
| Risk model approves | `risk_level <= max_acceptable_risk` (default: HIGH blocks, ELEVATED and below pass) |
| Required data is fresh/validated | fraction of `excluded_departments` (those with no usable data this cycle) stays under `max_excluded_fraction` (default 50%) |

All four thresholds are constructor parameters, not hardcoded — a stricter
desk might want `min_confidence=80` or to treat ELEVATED risk as a block too.

## Alert content

`format_alert_message()` builds exactly what the spec asks for: Asset,
Bias, Confidence, Risk, Timestamp, the trade thesis, and up to 3 each of
the top catalysts/risks — via plain string formatting (Markdown, since
Telegram renders it), no templating library, consistent with Phase 7's
trade-thesis/committee-summary approach.

## `telegram/telegram_alerter.py`

A thin wrapper around Telegram's free Bot API (`sendMessage`), using
`requests` (already a dependency — no new one added). Deliberately **not**
a `core.DataSource` subclass: `DataSource` is for pulling data INTO the
platform through the integrity-gated pipeline; `TelegramAlerter` pushes
data OUT after a decision has already been made. Conflating the two
would blur what `DataIntegrityManager` is actually gating.

A failed send raises `TelegramError` rather than failing silently —
`ChiefExecutionOfficer.process()` catches it and records it on the
returned `ExecutionDecision.send_error`, so "the gate passed but the
message didn't actually go out" is always visible and auditable, never a
silent no-op.

## Why `ExecutionDecision` is its own model, not bolted onto `StrategyReport`

It answers a different question than everything upstream of it — not
"what does the platform think" (that's `StrategyReport`) but "should a
human be notified right now" — and it's useful to keep every decision,
including blocked ones, for audit (pairs naturally with Phase 8's
`ChiefLearningOfficer`, though wiring execution decisions into persistence
is a natural next step rather than something this phase does automatically).

## What's demonstrated in Phase 9

- `scripts/demo_execution_officer.py` — two illustrative scenarios, one
  that clears every threshold (shows the exact message that would be sent)
  and one that's blocked on three separate grounds simultaneously (low
  confidence, high risk, and missing department data), proving each
  blocking reason is independently detected and all are reported together.
  The demo never sends a real Telegram message unless `--send-real` is
  passed with real credentials configured — a deliberate safeguard against
  accidentally spamming a real chat while testing.
- 17 new tests (207 total): every individual gating condition in isolation,
  multiple simultaneous blocking reasons, message-content checks, and
  `process()`'s send/no-send/send-failure paths with the Telegram call
  itself mocked

## What's NOT in Phase 9 (coming later)

- The dashboard (Phase 10) and scheduled orchestration/automation (Phase 11)
  — the only two things left per the original roadmap
- Automatically wiring `ExecutionDecision`s into `ChiefLearningOfficer`'s
  persistence (both exist now; connecting them is straightforward future work)
- Rate-limiting / de-duplication of repeated alerts for the same asset
  across consecutive cycles (a real deployment would want this; not built yet)
