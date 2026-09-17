# Configuration Guide

All configuration is via environment variables (`.env` locally; real secrets
in GitHub Actions/host secrets in production). See `.env.example` for the
full list.

| Variable            | Required for Phase 1? | Purpose                                                   |
|----------------------|:---:|------------------------------------------------------------|
| `FRED_API_KEY`       | Optional | Needed for `FredConnector` to return real data. Free key. |
| `SEC_USER_AGENT`     | Optional (needed for Phase 4 equity data) | SEC requires a descriptive User-Agent with real contact info, e.g. `"AI CFO Platform you@example.com"` — requests without one are commonly rejected. |
| `EIA_API_KEY`        | Optional (Commodity Fundamentals for energy) | Free key from https://www.eia.gov/opendata/register.php — used for Crude Oil/Natural Gas inventory data. Without it, those factors degrade to a missing-data gap. |
| `NEWS_RSS_URL`       | Optional (Phase 5 sentiment data) | Public market-news RSS feed. Defaults to MarketWatch's MarketPulse feed if left blank — confirmed via live testing to return genuinely market-relevant headlines (their earlier "top stories" feed, used as the default until this was found, was confirmed twice to return 0 of 10 market-relevant headlines — see `docs/ARCHITECTURE_NEWS_FEED_FIX.md`). |
| `ENABLE_COMMERCIAL_POSITIONING_DISPLAY` | Optional (default `false`) | Shows Commercial (hedger) COT positioning as informational context on Chief Commodity/FX Analyst reports. Even when `true`, Commercial data never affects bias/confidence/overall market score — see `docs/ARCHITECTURE_COMMERCIAL_REMOVAL_FROM_COT.md`. |
| `TELEGRAM_BOT_TOKEN` | No (future phase) | Chief Execution Officer alerting |
| `TELEGRAM_CHAT_ID`   | No (future phase) | Chief Execution Officer alerting |
| `ANTHROPIC_API_KEY`  | No (future phase) | AI-generated agent summaries |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | No (execution layer) | Broker credentials for `brokers/alpaca_connector.py`. **Safety note**: there is no `.env`-configurable live-trading flag anywhere — `AlpacaConnector` always defaults to paper trading; live trading requires `live_trading_confirmed=True` passed explicitly in code every time. See `docs/ARCHITECTURE_EXECUTION_LAYER.md`. |
| `MIN_DATA_QUALITY`   | Optional (default 60) | Minimum 0-100 quality score for a dataset to be `is_usable()` |
| `LOG_LEVEL`          | Optional (default INFO) | Standard Python logging level |

## Per-dataset TTL overrides

Default refresh intervals per data category live in
`config/refresh_intervals.py` and follow the spec's defaults (e.g. stock/
futures prices 30-60s, crypto 5-15s, COT weekly). Override per-registration:

```python
manager.register(
    "PRICE_SPY",
    primary=YahooConnector(ticker="SPY"),
    ttl_seconds=30,   # override the connector's own default_ttl_seconds
)
```

## Registering backup sources

```python
manager.register(
    "CRYPTO_BTC",
    primary=BinanceConnector(...),      # Phase 2+
    backups=[CoinGeckoConnector(...)],  # tried in order if primary fails
)
```

## Quality threshold

`DataIntegrityManager(min_quality_threshold=60)` sets the default bar for
`.get_or_raise()`. Individual calls to `dataset.is_usable(min_quality=...)`
can use a stricter or looser bar per use case (e.g. the Chief Execution
Officer should likely require a higher bar than a background monitoring
dashboard).

## FOMC meeting dates (for dynamic regime weighting)

`config/fomc_meeting_dates.py`'s `FOMC_MEETING_DATES` list ships EMPTY —
it's not a `.env` secret, but a code file you maintain yourself with the
real FOMC schedule from
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm. With it
empty, `agents.market_regime.classify_regime()` simply never detects an
FOMC week — the honest, correct behavior until you fill it in. See
`docs/ARCHITECTURE_FUNDAMENTAL_SCORING_ENGINE.md` for why this wasn't
pre-filled with guessed dates.
