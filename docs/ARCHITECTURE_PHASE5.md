# Architecture — Phase 5: Chief Sentiment Officer & Chief Technical Officer

## Chief Technical Officer (`agents/chief_technical_officer.py`)

One instance per ticker (same shape as the Phase 3/4 per-market agents),
scoring three components against daily closes from the new
`YahooHistoryConnector`:

- **RSI(14), 20% weight** — momentum. Also the source of this agent's risk
  flag: RSI ≥ 70 (overbought) or ≤ 30 (oversold) sets `risk_level` to
  `ELEVATED`, independent of bias direction — the same "flag the crowd
  extreme regardless of which way the bias points" principle Phase 3 (COT
  positioning) and Phase 4 (funding rate) established, applied here to a
  technical rather than positioning signal.
- **MACD histogram, 40% weight** — trend acceleration/deceleration.
  Important nuance surfaced while testing this: a perfectly linear
  (constant-slope) price trend produces a histogram of ~0 once the MACD
  line stabilizes, because MACD measures whether the trend is *speeding up
  or slowing down*, not the trend's mere existence — a real trend still
  needs the SMA component below to register as bullish/bearish. The
  histogram is normalized by price level (`histogram / latest_close`) so
  it's comparable across assets of very different magnitudes.
- **SMA(20) vs SMA(50) trend, 40% weight** — is price in a sustained
  up/downtrend. This is what actually captures "the market is trending",
  as distinct from MACD's "is that trend accelerating."

`agents/technical_indicators.py` implements RSI, MACD, and SMA in pure
Python (no numpy/pandas indicator libraries) — every formula is inspectable
line-by-line, matching the project's "one-sentence explainable" scoring
philosophy used everywhere else.

Per the spec, the Chief Technical Officer's job is to "confirm or reject
the fundamental thesis" — that reconciliation across departments is
explicitly the Chief Strategy Officer's job (Phase 7), not this agent's.
This agent produces its own independent read only.

## Chief Sentiment Officer (`agents/chief_sentiment_officer.py`)

Primary signal: news headline sentiment, scored by a small curated
keyword lexicon (`agents/sentiment_scoring.py`) rather than an ML model —
consistent with the project's preference for auditable scoring over
black-box ones. Weight is 100% when used alone, or 60% when a `cot_key` is
also supplied.

Optional secondary signal: the SAME CFTC COT dataset a Chief Commodity/FX
Analyst is already reading for a given market, reinterpreted through a
"crowd sentiment" lens (40% weight) rather than the pure directional-bias
lens those agents use. This is a deliberate architecture point: registering
one COT dataset in the `DataIntegrityManager` and pointing *multiple*
agents at the same key costs nothing extra — the manager's caching means
the second agent gets the cached dataset, not a second live fetch.
`net_position_trend_score` and `positioning_extremity_flag` (Phase 3) are
reused directly rather than reimplemented.

## New connector: `connectors/news_connector.py`

Free, public RSS feed, parsed with the standard library's `xml.etree`
(no new dependency). Configurable via `NEWS_RSS_URL` (default: MarketWatch's
public top-stories feed). Deliberately doesn't try to extract a trustworthy
single "as of" timestamp from the feed itself — RSS providers are
inconsistent about this — and instead timestamps by fetch time, same as the
Phase 1 `YahooConnector` does for live quotes.

## New connector: `connectors/yahoo_history_connector.py`

Separate from Phase 1's `YahooConnector` (which fetches only the latest
single price at a 45s TTL). This one fetches a window of daily closes at a
much longer TTL (1 hour) — technical indicators built on daily bars don't
need per-minute refreshing, and treating them as if they did would just
burn API calls for identical data.

## What's demonstrated in Phase 5

- `scripts/demo_sentiment_technical_agents.py` — registers a real news feed
  and real SPY price history, runs both agents end-to-end
- 39 new tests (132 total): technical indicator math against known
  sequences (including the MACD-on-linear-trend edge case above), both new
  connectors (HTTP/yfinance mocked), sentiment keyword scoring, and both
  agents' bullish/bearish/overbought/crowded/missing-data scenarios

As with every prior phase, this sandbox has no egress to the configured
news feed or Yahoo Finance, so the demo here shows both agents at
`confidence: 0.0`, `risk_level: high` — correct behavior when sources are
unreachable. Run it anywhere with normal internet access for real output.

## What's NOT in Phase 5 (coming later)

- Four more Chief Officers (Risk, Strategy, Learning, Execution)
- Fear & Greed index, ETF/fund flows, put/call ratio, options positioning
  for sentiment; Market Structure, Elliott Wave, Wyckoff, Volume Profile,
  Anchored VWAP, OBV, ATR, Fair Value Gaps, Order Blocks, multi-timeframe
  analysis for technicals
- Any persistence, alerting, or dashboard surfacing of these reports
- The actual fundamental-vs-technical reconciliation the spec describes —
  that's the Chief Strategy Officer's job (Phase 7)
