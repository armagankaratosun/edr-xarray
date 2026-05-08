# Task-18 Learnings: Subclass Extensibility Tests

## Hook contract (verified)
EdrDataStore exposes 7 documented hooks, all overridable via standard Python subclassing:
- `_request` — HTTP layer (auth/retry injection)
- `_parse_collection_metadata` — extract custom metadata fields
- `_negotiate_output_format` — format negotiation policy
- `_build_cube_url` — non-standard URL routing
- `_parse_coveragejson` — server-specific CoverageJSON dialects
- `_translate_indexer` — inject static query filters
- `_discover_axes` — alternative axis discovery strategies

## pytest-httpserver gotchas confirmed
- Header matching IS case-insensitive: `headers={"x-api-key": ...}` matches `X-Api-Key:`
- Two-handler pattern (ordered + broad) needed when same path serves probe AND data fetch
- `expect_ordered_request` fires once, `expect_request` is broad fallback

## Override propagation (verified)
- `_request` override propagates auth headers through ALL transport calls (metadata + probe + data fetch)
- `_translate_indexer` override is invoked by `EdrBackendArray._raw_indexing_method` because `store=self` reference is preserved
- `_build_cube_url` override affects probe discovery too (probe uses `self._cube_url`)
- `_parse_coveragejson` override intercepts all CoverageJSON parsing including the data-fetch path

## Test pattern
Use `_setup(httpserver, collection_id)` helper to register meta + cube endpoints with consistent ID-isolated paths. This avoids ordering issues across the 8 tests in one test session.
