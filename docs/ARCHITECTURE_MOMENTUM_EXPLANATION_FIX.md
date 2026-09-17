# A real bug: Trade Decision Engine's four momentum explanations were all identical

## How this was found

Live testing showed all four "Score Momentum" sections — Fundamental,
Technical, Risk, and Overall — displaying the exact same three-bullet
"Why" explanation:

```
Fundamental  Why: [COT positioning risk] [crowded long risk] [volatility risk]
Technical    Why: [COT positioning risk] [crowded long risk] [volatility risk]
Risk         Why: [COT positioning risk] [crowded long risk] [volatility risk]
Overall      Why: [COT positioning risk] [crowded long risk] [volatility risk]
```

That's actively misleading, not just repetitive: the Technical Score is
computed purely from RSI/MACD/SMA price data (see
`docs/ARCHITECTURE_TRADE_DECISION_TECHNICAL_FIX.md`) and has nothing to
do with COT positioning — showing COT-based reasoning as "why" the
Technical score moved implies a connection that doesn't exist.

## Root cause

`agents/chief_trade_decision_officer.py` called `_momentum()` four times
— once per score — but passed the exact same merged, whole-decision
`catalysts`/`risks` lists to all four:

```python
fund_momentum = self._momentum(asset_or_theme, "fundamental_score", fund_score, catalysts, risks)
tech_momentum = self._momentum(asset_or_theme, "technical_score", tech_score, catalysts, risks)
risk_momentum = self._momentum(asset_or_theme, "risk_score", risk_score_value, catalysts, risks)
overall_momentum = self._momentum(asset_or_theme, "overall_score", overall, catalysts, risks)
```

`agents/score_momentum.py`'s `explain_momentum()` itself has no way to
know which component it's explaining — it just returns the first 3
items of whatever list it's handed. With every call receiving the same
list, every explanation was identical by construction.

## The fix

Component-specific catalysts/risks are now built before the four calls,
reusing data the method already computes:

- **Fundamental**: filtered from `reports` to only the departments in
  `fund_contrib` (the same list already used to compute the Fundamental
  Score itself)
- **Technical**: taken directly from the synthetic technical report's
  own `catalysts`/`risks` (built from real RSI/MACD/SMA price data, not
  from any of `reports`)
- **Risk**: filtered from `reports` to only the departments in
  `risk_contrib`
- **Overall**: unchanged — still uses the full merged list, since "why
  did the OVERALL score move" is legitimately explained by everything
  together

## A related question investigated and found to be a non-issue

The same live run showed "Why any unchecked items failed" rendering as
empty bullets. Reconstructed directly and rendered through the real
`build_entry_confirmation()` — it produces completely real text
(`"Momentum (MACD) does not yet confirm the structural trend direction"`,
etc.). Same root cause as the earlier Chief Risk Fundamentals Officer
finding: this section is inside a `st.expander(expanded=False)`, and
copying the page before clicking it open only captures the bullet
markers, not the text hidden inside. Not a bug.

## Testing

`test_momentum_explanations_are_component_specific_not_all_identical`
proves the fix directly: a Fundamental-only risk (COT positioning
language) appears in Fundamental's explanation but is proven absent from
Technical's — the two no longer bleed into each other. 612 tests total,
all passing, zero regression to any existing behavior.
