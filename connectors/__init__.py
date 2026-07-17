"""
Connectors: thin adapters between external APIs and core.DataSource.

Each connector ONLY fetches and does a cheap shape check. Freshness/quality
scoring and caching are handled centrally by core.DataIntegrityManager —
do not duplicate that logic here.
"""
