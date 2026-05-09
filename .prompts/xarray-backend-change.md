---
description: Checklist for changing the xarray backend entrypoint, store, or backend array
agent: build
---

# xarray Backend Change

Use this before editing `backend.py`, `store.py`, `array.py`, or builder/indexing
code.

## Contracts To Preserve

- `xr.open_dataset(url, engine="edr", ...)` remains the primary user API.
- `open_dataset` does not implement xarray-owned `chunks` or `cache`.
- Xarray decoder kwargs remain accepted for compatibility unless a deliberate
  API change removes them.
- `drop_variables` works after dataset construction.
- `guess_can_open`, `description`, `url`, and the entry point stay correct.
- `Dataset.set_close()` remains connected to store close behavior.
- `BackendArray` shape and dtype inspection stays lazy.
- Data fetches happen through backend array indexing only.
- Store hooks route external metadata/cube behavior as documented.

## Tests To Add Or Update

- Backend registration and `open_dataset` behavior.
- Exact request counts for open, probe, compute, repeated compute, `.isel()`,
  `.sel()`, and `.load()` where relevant.
- Hook routing through subclass overrides.
- Dask `chunks=...` behavior and pickle round-trips when serialization-sensitive
  state changes.
- xarray object equality using `xarray.testing` helpers when datasets are
  compared.

## Verification

Run focused backend/laziness tests, then the full local gate.
