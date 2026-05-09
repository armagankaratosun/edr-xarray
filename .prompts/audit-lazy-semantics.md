---
description: Audit xarray lazy loading and HTTP request behavior
agent: build
---

# Audit Lazy Semantics

Use this after changes that touch metadata loading, axis discovery, indexing,
transport, backend arrays, Dask, or xarray dataset construction.

## Expected Behavior

- `discovery="metadata_only"` opens with metadata only.
- `discovery="probe"` opens with metadata plus one minimal cube probe.
- Shape, dtype, dims, coords, attrs, and variable inspection do not fetch user
  data.
- `.values`, `.load()`, `.compute()`, and concrete xarray indexing fetch data.
- Indexing narrows EDR query parameters where possible.
- Repeated fetch behavior remains explicit and tested; do not introduce hidden
  caching unless xarray owns it and tests document it.

## Audit Process

- Read the touched code path from `EdrBackendEntrypoint` through `EdrDataStore`
  and `EdrBackendArray`.
- Write down expected request sequence before running tests.
- Use `pytest-httpserver` request logs to assert exact paths and query strings.
- Include Dask and pickle checks if serialized backend state may be affected.

## Verification

Run:

```bash
uv run pytest tests/test_lazy_semantics.py tests/test_array.py tests/test_store.py tests/test_pickle_dask.py -v
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```
