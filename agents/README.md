# agents/

Reserved for Phase 2+: each Chief Officer (Macro, Commodity, Equity, FX,
Crypto, Bond, Sentiment, Technical, Risk, Strategy, Learning, Execution)
gets its own module here. Every agent will consume data exclusively through
`core.DataIntegrityManager` — never directly from a connector.
