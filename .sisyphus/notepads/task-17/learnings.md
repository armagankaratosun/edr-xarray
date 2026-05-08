# Task-17 learnings

## xarray lazy-array wrapping chain

For a Variable created with `xr.Variable(dims, data=indexing.LazilyIndexedArray(backend))`:

- `xr.open_dataset(...)` (default `cache=True`) wraps the chain as:
  `MemoryCachedArray -> CopyOnWriteArray -> LazilyIndexedArray -> EdrBackendArray`
- `xr.open_dataset(..., cache=False)` skips MemoryCachedArray:
  `CopyOnWriteArray -> LazilyIndexedArray -> EdrBackendArray`
- Walk to the inner BackendArray via `arr.array` (each wrapper exposes `.array`).
- Use `Variable._data` (private) to inspect the chain without triggering load;
  `Variable.data` may eagerly materialize.

## Pickle behavior

- `EdrDataStore.__getstate__` drops `_transport`; `__setstate__` builds a fresh
  `Transport(timeout=...)` directly (does not delegate to Transport.__setstate__).
- `EdrBackendArray.__getstate__` keeps the store back-reference. After unpickle
  the array can issue HTTP via the store's fresh transport.
- An `xr.Dataset` opened by the EDR backend pickles fine despite holding a
  `set_close(store.close)` bound-method reference, because `EdrDataStore` is
  itself picklable.

## Dask integration test

- `pytest.importorskip("dask", reason="dask not installed")` is the cheapest skip.
- `xr.open_dataset(url, ..., chunks={"t": 1})` produces a `dask.array.Array`
  for variables that include the `t` dim. The dim name must match `axis.name`
  produced by discovery — in probe mode this is the CoverageJSON `axisNames`
  entry (e.g. `"t"` not `"time"`).

## pytest-httpserver for repeated fetches

- `expect_ordered_request(...)` matches once, in order.
- `expect_request(...)` is a flexible (repeatable) handler.
- Common pattern for tests that pickle then refetch: register an ordered
  metadata + ordered probe, then a flexible cube handler for any further
  fetches initiated by the unpickled Dataset.
