# Task 16 — Lazy Semantics Test Learnings

- xarray `open_dataset` defaults to `cache=True`, which wraps backend arrays with `MemoryCachedArray`. After the first `.values` call, `_ensure_cached` replaces the lazy wrapper with the materialized numpy result, so subsequent `.values` calls return cached data WITHOUT another HTTP fetch. To prove repeated fetches with no caching, pass `cache=False` to `xr.open_dataset`. The EDR backend itself does not cache.
- pytest-httpserver pattern for testing the open path: register `expect_ordered_request` for metadata + probe (consumed in order), then add `expect_request` (unordered, repeatable) for any subsequent data fetches. After both ordered handlers are consumed, additional cube requests fall through to the unordered handler.
- `discovery="metadata_only"` mode produces axes with names `("t", "y", "x")` — same names as probe mode for our cov_grid_3d.json fixture — but built from `extent.spatial.bbox` and `extent.temporal.values` without any HTTP probe. Exactly 1 HTTP request on open.
- `discovery="probe"` issues exactly 2 requests on open: metadata GET + cube probe GET (with full bbox + datetime).
- `isel(x=0).values` produces a degenerate-x bbox `"10.0,40.0,10.0,41.0"` in the cube data fetch query string (`spatial_full=False` because x indexer is an int, not a full slice). The probe URL uses the full bbox `"10.0,40.0,11.0,41.0"`.
- Inspecting requests: `httpserver.log` is `list[tuple[Request, Response]]`. `request.path` gives URL path; `request.query_string.decode()` gives the URL-decoded query string.
