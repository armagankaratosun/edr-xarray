# Test Plan

The default test suite is offline and deterministic. Live EDR server checks are
opt-in.

## Required Local Gate

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pyright --verifytypes edr_xarray --ignoreexternal
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

## Test Focus

- Backend registration and `open_dataset` behavior.
- Laziness and exact HTTP request counts.
- CoverageJSON parsing, null handling, axis order, and malformed payload errors.
- Metadata parsing and cube URL construction.
- Query encoding and xarray indexer translation.
- Store hook extensibility and subclass routing.
- Transport ownership, error mapping, and JSON parsing.
- Pickle and Dask compatibility.
- Version alignment between `VERSION`, package metadata, and
  `edr_xarray.__version__`.

## Live Tests

Live tests require `EDR_LIVE_URL` and are excluded by default:

```bash
EDR_LIVE_URL=http://localhost:8000 uv run pytest -m live
```

Do not make network access part of the default suite.

## Notebook Checks

Validate notebooks as JSON after edits. Do not execute live endpoint cells by
default; run them only when an appropriate EDR endpoint is configured.
