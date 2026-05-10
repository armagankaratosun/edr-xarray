# edr-xarray

Lazy [xarray](https://xarray.dev) backend for [OGC API - Environmental Data Retrieval (EDR) 1.1](https://docs.ogc.org/is/19-086r6/19-086r6.html) `/cubes` endpoint.

**Status**: alpha (v0.1.2)

## Overview

`edr-xarray` registers `engine="edr"` with xarray, letting you open any EDR 1.1-compliant
collection as a lazy `xarray.Dataset`. Data is only fetched from the server when you
call `.values`, `.load()`, or `.compute()` on a `DataArray` — opening the dataset
issues lightweight metadata requests for the collection, for the selected instance when
`instance=` is supplied, and optionally one axis-discovery probe.

Designed to be subclassed: downstream packages can override transport, metadata parsing,
CoverageJSON handling, and URL routing via seven documented hook methods on `EdrDataStore`.

## Installation

```bash
pip install edr-xarray
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add edr-xarray
```

Requires Python 3.11 or 3.12 and xarray 2024.6+.

## Usage

```python
import xarray as xr

# Open an EDR collection (lazy — metadata plus an optional axis probe on open)
ds = xr.open_dataset(
    "https://edr.example.com/collections/temperature_2m",
    engine="edr",
    parameter_names=["t2m"],
    bbox=(-3.5, 50.2, -2.1, 51.0),
    datetime="2023-01-01T00:00:00Z/2023-01-07T00:00:00Z",
)

# Inspect structure (no data fetched yet)
print(ds.dims)      # {'t': 168, 'y': 50, 'x': 50}
print(ds.data_vars) # {'t2m': <xarray.Variable>}
print(ds["t2m"].attrs)  # {'units': 'K', 'long_name': 'Air temperature', ...}

# Fetch a subset (triggers one EDR /cube query)
sub = ds["t2m"].sel(x=slice(-3.0, -2.5)).load()
print(sub.shape)   # (168, 50, N)
```

### Discovery modes

By default (`discovery="probe"`), `open_dataset` issues one extra GET request to the cube
endpoint to discover the exact grid axes (resolution, coordinate arrays). Two alternative modes:

When `bbox=`, `datetime=`, or `z=` are supplied, probe discovery uses those open-time
subsets to declare xarray coordinates. For collections with long time axes and abbreviated
temporal metadata, pass a bounded `datetime` interval so `ds.t` matches the analysis window.
If the server advertises explicit temporal values, those values are used for the time
coordinate. If it only advertises a temporal interval and no `datetime=` is supplied,
`edr-xarray` opens the first instant as a small, consistent default.

```python
# metadata_only: use only selected collection/instance metadata (bbox + temporal extent)
# Fewer requests but lower resolution coordinate arrays
ds = xr.open_dataset(url, engine="edr", discovery="metadata_only")

# strict: requires explicit temporal/vertical coordinate values in metadata
# and uses spatial bbox endpoints for x/y axes
ds = xr.open_dataset(url, engine="edr", discovery="strict")
```

### Collections with instances (forecast runs)

When `instance=` is supplied, `edr-xarray` fetches the selected instance metadata
and builds coordinates, variables, attributes, fallback `bbox`, and fallback
`datetime` from that instance. Data values are still lazy and are fetched only
when xarray requests concrete array values.

```python
ds = xr.open_dataset(
    "https://edr.example.com/collections/model_output",
    engine="edr",
    instance="f024",
    parameter_names=["temperature"],
)
```

### Vertical levels (z)

```python
# Single level
ds = xr.open_dataset(url, engine="edr", z=850)

# Level range
ds = xr.open_dataset(url, engine="edr", z="1000/500")
```

### Authentication

Pass a pre-configured `httpx.Client` for any auth style (API key, Bearer token, Basic, mTLS):

```python
import httpx
import xarray as xr

client = httpx.Client(headers={"X-Api-Key": "your-key-here"})
ds = xr.open_dataset(url, engine="edr", session=client)
```

The injected client is not closed by `edr-xarray` — manage its lifecycle yourself.

### Dask integration

Install the optional Dask extra before opening datasets with `chunks=...`:

```bash
pip install "edr-xarray[dask]"
```

```python
# Chunk along time for out-of-core analysis
ds = xr.open_dataset(url, engine="edr", chunks={"t": 1})
result = ds["t2m"].mean(dim="t").compute()
```

### Subclassing

Override `EdrDataStore` hooks to customize transport, URL routing, or response parsing:

```python
from typing import Any, Mapping
import httpx
from edr_xarray import EdrDataStore

class AuthenticatedStore(EdrDataStore):
    def _request(
        self, method: str, url: str, *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        merged = dict(headers or {})
        merged["X-Api-Key"] = "my-secret"
        return super()._request(method, url, params=params, headers=merged)
```

Available hooks: `_request`, `_parse_collection_metadata`, `_negotiate_output_format`,
`_build_cube_url`, `_parse_coveragejson`, `_translate_indexer`, `_discover_axes`.

See `tests/test_subclass_extensibility.py` for full usage examples.

## Examples

Guided Jupyter notebooks live in [`examples/`](examples/README.md). They use
live EDR endpoints and make the lazy open, indexing, and fetch boundaries
explicit.

## Limitations (v1)

- Only `/cubes` queries are supported (no `/position`, `/area`, `/trajectory`, etc.).
- Only CoverageJSON responses (Grid domain, flat NdArray values).
- `bbox` input uses CRS84 axis order `(lon_min, lat_min, lon_max, lat_max)`.
- No antimeridian-crossing bbox support.
- No exotic z syntax (`R14/.../...`, comma-separated level lists).
- No automatic retry, caching, or async HTTP client.

## Development

```bash
git clone https://github.com/armagankaratosun/edr-xarray
cd edr-xarray
uv sync
uv run pytest
```

Run type checks and lint:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pyright --verifytypes edr_xarray --ignoreexternal
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

Run opt-in live tests against an EDR server:

```bash
EDR_LIVE_URL=http://localhost:8000 uv run pytest -m live
```

## License

Apache-2.0
