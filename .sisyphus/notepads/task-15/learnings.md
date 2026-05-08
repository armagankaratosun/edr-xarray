# Task 15 — Integration Tests Learnings

- Discovered axis order in xarray Dataset comes from `cov.axis_names` in the probe response — NOT from metadata. With COV_3D having `axisNames: ["t","y","x"]`, dims become `("t","y","x")` (not `"time"`).
- 4D probe discovery works without `extent.vertical` in metadata: `_probe_axes` reads axes directly from the CoverageJSON response. The metadata fixture can stay 3D-shaped as long as the probe returns COV_4D.
- `_raw_indexing_method` returns the FULL CoverageJSON range array regardless of indexer key (the slicing is delegated to the EDR server via query params). With a mock server returning the full fixture, `.isel(z=1).values` would mismatch shape — so 4D test asserts on full `.values` shape `(1,3,2,2)` instead of slicing.
- pytest-httpserver matching order: `expect_ordered_request` is consumed in registration order, then `expect_request` (unordered, repeatable) catches the rest. Pattern: register ordered metadata + ordered probe-cube, then add unordered cube for subsequent data fetches.
- Header-matching in pytest-httpserver is case-insensitive, so injecting `httpx.Client(headers={"X-Api-Key": "secret"})` matches `expect_request(headers={"x-api-key": "secret"})`.
- `len(httpserver.log)` returns total request count (each entry is `(Request, Response)` tuple).
- For `instance="f024"`, `cube_url()` rewrites the trailing `/cube` to `/instances/f024/cube`. The metadata's cube href must end with `/cube` for this routing to work.
