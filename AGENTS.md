# Agent Guide

This repository is a Python package that registers an xarray backend engine for
OGC API - Environmental Data Retrieval (EDR) `/cubes` endpoints. Treat the xarray
backend contract, lazy loading behavior, and subclass hook surface as the core
architecture.

## Guidelines

- CRITICAL: Preserve lazy semantics.
  Opening a dataset may fetch collection metadata and, in `discovery="probe"`,
  one axis-discovery cube probe. It must not fetch user data until xarray indexes
  or computes a variable through `.values`, `.load()`, or `.compute()`.

- CRITICAL: Preserve the xarray backend boundary.
  `EdrBackendEntrypoint.open_dataset()` accepts xarray-compatible decoder
  keyword arguments, but xarray owns `chunks` and `cache`. Do not implement
  custom chunk/cache handling in the backend entrypoint.

- CRITICAL: Preserve subclass extensibility.
  All external cube traffic must route through the documented `EdrDataStore`
  hooks: `_request`, `_parse_collection_metadata`, `_negotiate_output_format`,
  `_build_cube_url`, `_parse_coveragejson`, `_translate_indexer`, and
  `_discover_axes`.

- CRITICAL: Do not suppress warnings, lint errors, type errors, or test failures
  unless the suppression is the correct semantic choice. Prefer fixing the root
  cause. If a suppression is required, make it narrow and explain why it is
  still correct.

- IMPORTANT: This package is pre-1.0. Breaking changes are allowed when they
  simplify the design or correct bad behavior, but the same change must update
  tests, README/docs, examples, and release notes as appropriate.

- IMPORTANT: Keep helpers pure where they are pure today. Metadata parsing,
  CoverageJSON parsing, query encoding, axis discovery helpers, and index
  translation should not gain hidden I/O, logging, caches, or global state.

- IMPORTANT: Keep Dask and pickle compatibility in mind. Backend arrays and
  stores must not retain unpickleable owned resources after serialization; owned
  HTTP clients are restored lazily, while injected sessions remain caller-owned.

- IMPORTANT: Derived values have one source of truth. `VERSION` is canonical for
  releases; package metadata, `edr_xarray.__version__`, changelog entries, docs,
  and tags must agree with it.

- IMPORTANT: Avoid process-ephemeral wording in code, comments, docs, plans, and
  commit messages. Prefer names that describe what a thing is or does rather than
  references such as "phase 2", "round 1", or "after review feedback".

## Project Map

- `README.md` - user-facing overview, installation, usage, limitations
- `CONTRIBUTING.md` - contributor workflow and local checks
- `plans/MOTIVATION.md` - why the package exists
- `plans/DESIGN.md` - architecture and major contracts
- `plans/STYLE.md` - Python/xarray coding conventions
- `plans/TEST.md` - test strategy and coverage expectations
- `plans/TODO.md` - accepted backlog
- `plans/IDEAS.md` - possible future work
- `plans/DONE.md` - notable completed work
- `CHANGELOG.md` - release history
- `VERSION` - canonical package version

Follow `plans/DESIGN.md` and `plans/STYLE.md` when changing code.

## Python And xarray Style

- Follow PEP 8 naming and PEP 484 typing. Prefer clear snake_case functions,
  CapWords classes, module constants in UPPER_CASE, and public names that reflect
  user behavior rather than implementation details.
- Use `from __future__ import annotations`, `collections.abc` collection types,
  `str | None` style unions, dataclasses for plain immutable records, and
  `Protocol` for structural hook contracts when it clarifies dependencies.
- Prefer composition over inheritance. Use GoF pattern names only when they
  clarify an existing design; do not add pattern-shaped abstractions for their
  own sake.
- Keep functions focused and readable. Extract helpers when they remove real
  complexity or preserve a clear module boundary.
- Comments and docstrings should explain contracts, constraints, and why a
  choice is non-obvious. Avoid comments that merely restate the next line.
- Use xarray testing helpers such as `xarray.testing.assert_identical` when
  comparing full xarray objects.
- Use xarray's explicit indexing adapter for backend indexing. Do not manually
  accept arbitrary NumPy/xarray indexer shapes unless the xarray contract is
  preserved and tested.

## Required Checks

Run focused tests first for the touched behavior, then run the full local gate:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pyright --verifytypes edr_xarray --ignoreexternal
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

Use live tests only when explicitly requested or when `EDR_LIVE_URL` is set:

```bash
EDR_LIVE_URL=http://localhost:8000 uv run pytest -m live
```

## Documentation And Examples

- Update README, plans, docs, and examples when behavior changes.
- Examples live as Jupyter notebooks under `examples/`. Do not add a parallel
  example script tree for normal package usage.
- Examples must show fetch boundaries explicitly. Inspecting structure should
  stay lazy; `.values`, `.load()`, and `.compute()` are the visible data-fetch
  points.
- New public options or hooks need tests, user-facing documentation, and clear
  error behavior.

## Release Rules

- Tags use plain `X.Y.Z` without a leading `v`.
- `VERSION` is the release source of truth.
- Before a release, verify the working tree is clean, `uv build` reads the
  expected version, the full check gate passes, and `CHANGELOG.md` has an entry.
