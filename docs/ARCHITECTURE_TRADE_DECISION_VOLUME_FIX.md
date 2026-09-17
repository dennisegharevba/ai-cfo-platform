# Trade Decision Engine — a real duplication found via live dashboard review

## What was found

Looking at a real Trade Decision Engine result on the dashboard: the
Entry Confirmation Checklist showed **Market structure**, **Breakout**,
and **Volume** as three separate rows, each with its own checkmark —
appearing to be three independent confirmations. They were not. All
three were driven by the exact same underlying value: whether the MACD
histogram agreed with the SMA trend direction — an explicitly documented
placeholder from an earlier phase, put in place "until real detectors
exist." Showing the same signal three times under different names
created a misleading impression of more confirmation than genuinely
existed.

## The fix, in two parts

**1. Volume is now genuinely real**, not a proxy. `decide()` already
received real price history (including volume, since that was added to
the connector earlier the same day) — the data needed was already
flowing through, just unused for this purpose.
`agents/trade_scoring.py`'s `build_entry_confirmation()` takes an
optional `volumes_newest_first` parameter and uses the platform's real
volume confirmation logic
(`agents.technical_indicators.volume_confirmation_ratio()` — see
`docs/ARCHITECTURE_VOLUME_CONFIRMATION.md`) when available. Fully
backward compatible: omitting the parameter falls back to exactly the
previous proxy behavior, proven directly by a dedicated test.

No usable volume data (the same fairness case as the opportunity
screener — common for FX pairs) falls back to the same proxy rather
than being treated as a failed check, so an asset class is never
penalized for a data source's own coverage gap.

**2. Breakout was removed**, not fixed — it was never possible for it to
disagree with Market Structure (both were always the same value), so
building a genuinely independent breakout detector would mean building
real BOS/CHoCH-style structural detection — the same Smart Money
Concepts methodology already considered and deliberately set aside
earlier the same day for being more subjective and less rigorously
grounded than volume confirmation (see
`docs/ARCHITECTURE_VOLUME_CONFIRMATION.md`'s "what was deliberately not
built" section). Removing a duplicate row is a stronger, more honest fix
than leaving a row that can never provide new information.
`breakout_confirmed` is gone from `models/trade_decision.py`'s
`EntryConfirmation`, `agents/trade_scoring.py`, and the dashboard's
checklist rendering. `all_passed()`'s actual gating behavior is
unchanged — the two fields were never able to disagree, so removing one
changes nothing about when a trade is or isn't cleared for entry, only
the honesty of what's displayed.

## Verified

- A dedicated test proves the previous, pre-fix backward-compatible
  behavior: omitting volume data still makes `volume_confirmed` mirror
  `market_structure_confirmed` exactly as before
- A dedicated test proves the fix directly: with real, controlled
  below-average volume data, `market_structure_confirmed` stays `True`
  while `volume_confirmed` becomes `False` — genuinely decoupled, not
  secretly identical
- A dedicated test proves the fairness fallback: all-zero (unusable)
  volume data falls back to the proxy, never penalized
- An end-to-end smoke test through the real `ChiefTradeDecisionOfficer.decide()`
  entry point confirms the wiring works correctly outside of isolated
  unit tests, and confirms `breakout_confirmed` no longer exists on the
  result at all

## Testing

4 new tests in `tests/test_trade_scoring.py`, 3 existing tests updated
for the field removal. **780 tests total, all passing.**
