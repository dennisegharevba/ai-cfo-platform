# COT positioning: clarifying two genuinely different measurements

## How this was found

Not a bug — a real clarity gap caught via live testing. A live EUR/USD
run showed:

```
Current Non-Commercial net position is at the 25th percentile of the
last 8 COT reports (within a normal range for this window)
```

sitting right next to an overall bias score of exactly **-100.0**
(strongly bearish, the maximum possible magnitude). Read together, these
looked contradictory — "normal range" next to "maximally extreme."

## The investigation

Rather than assume this was a bug, the actual net-position numbers were
pulled live (`connectors/cot_connector.py` directly) and traced through
`agents/positioning_scoring.py`'s formula by hand. The real data:

```
2026-06-16: net +34,353  (oldest in the 8-week window)
2026-06-23: net +30,158
2026-06-30: net  +1,099
2026-07-07: net -16,227
2026-07-14: net -12,605
2026-07-21: net -41,338
2026-07-28: net -72,447
2026-08-04: net -58,091  (newest)
```

This is a genuine, severe reversal — from meaningfully net-long to
meaningfully net-short over 8 weeks — a real -269% swing relative to the
starting position. The -100.0 score is a correct, honest reflection of
that. Not a bug.

The percentile reading is ALSO correct: -58,091 (the current reading)
isn't the single most negative value in this exact 8-week window — the
prior week, -72,447, was more extreme. So "25th percentile, normal
range" is an accurate statement about where today sits relative to its
own recent range, even though the OVERALL trend across the full window
is severe.

**Both statements are true.** They measure two genuinely different
things:
- The bias score: the SIZE of the swing from the oldest to the newest
  reading in the window
- The percentile: where TODAY's reading ranks among all 8 readings in
  that same window

A severe trend and a "not currently at its own local extreme" position
are not mutually exclusive — but nothing in the generated text explained
that, so the two readings looked like they contradicted each other when
they didn't.

## The fix

Purely a wording change, in `agents/positioning_agent_base.py` — the
percentile evidence line now explicitly states it measures a different
question than the trend score above it, and that the two can genuinely
disagree without contradiction:

> "Current Non-Commercial net position is at the Nth percentile of the
> last M COT reports (...) — this measures where TODAY's position sits
> within its own recent range, a separate question from the overall
> multi-week TREND reported above; the two can genuinely disagree (e.g.
> a severe multi-week reversal that hasn't yet pushed the position to a
> new extreme within this specific window)"

No scoring logic changed at all — this is presentation-only, since the
investigation confirmed the underlying numbers were already correct.

## Testing

`test_percentile_evidence_clarifies_it_measures_something_different_from_the_trend_score`
reproduces the user's exact real EUR/USD data (the 8 net positions
above) and proves both the -100.0 score and the new clarifying language
appear together, exactly as they did live. 607 tests total, all passing,
zero change to any scoring behavior.
