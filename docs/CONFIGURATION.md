# Configuration Guide

All configuration is via environment variables (`.env` locally; real secrets
in GitHub Actions/host secrets in production). See `.env.example` for the
full list.

| Variable            | Required for Phase 1? | Purpose                                                   |
|----------------------|:---:|------------------------------------------------------------|
| `FRED_API_KEY`       | Optional | Needed for `FredConnector` to return real data. Free key. |
| `SEC_USER_AGENT`     | Optional (needed for Phase 4 equity data) | SEC requires a descriptive User-Agent with real contact info, e.g. `"AI CFO Platform you@example.com"` — requests without one are commonly rejected. |
| `TELEGRAM_BOT_TOKEN` | No (future phase) | Chief Execution Officer alerting |
| `TELEGRAM_CHAT_ID`   | No (future phase) | Chief Execution Officer alerting |
| `ANTHROPIC_API_KEY`  | No (future phase) | AI-generated agent summaries |
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
