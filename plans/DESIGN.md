# Design

`edr-xarray` is organized around a small xarray backend boundary and pure helper
modules.

## Architecture

- `EdrBackendEntrypoint` is the xarray plugin entrypoint registered as
  `engine="edr"`.
- `EdrDataStore` orchestrates metadata fetch, output-format negotiation, cube URL
  construction, axis discovery, lazy dataset assembly, close handling, and
  pickle restoration.
- `EdrBackendArray` is the lazy xarray `BackendArray`. It converts xarray
  indexing into EDR query parameters, fetches cube data, parses CoverageJSON, and
  returns NumPy arrays only when xarray asks for concrete values.
- Parser and encoder modules are pure: metadata, CoverageJSON, query encoding,
  axis classification, and index translation should remain deterministic and
  side-effect free.

## Core Contracts

- Opening a dataset is lazy with respect to data values. Metadata and optional
  probe requests are allowed; user data fetches happen through backend array
  indexing.
- xarray owns `chunks` and `cache`. Backend code may set
  `Variable.encoding["preferred_chunks"]`, but must not bypass xarray's chunking
  path.
- `Dataset.set_close()` must stay wired to store close behavior so xarray can
  release owned resources.
- Injected `httpx.Client` sessions are caller-owned and must not be closed by
  the package.
- Pickle round-trips must restore usable stores and arrays for Dask and
  multiprocessing workflows.
- The seven documented `EdrDataStore` hooks are the extension API. New behavior
  should preserve hook routing or deliberately update the hook contract with
  tests and docs.

## Compatibility

The package is pre-1.0. Public behavior can change when it improves the design,
but changes must be intentional, tested, and documented. Avoid expanding the
public API casually; prefer a small surface with clear extension points.
