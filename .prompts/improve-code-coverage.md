---
description: Measure coverage and add meaningful tests for uncovered behavior
agent: build
---

# Improve Code Coverage

Use this to improve branch and line coverage without adding low-value tests.

## Measure

```bash
uv run pytest --cov=src/edr_xarray --cov-report=term-missing --cov-fail-under=95 -v -m "not live"
```

## Analyze

For every uncovered path, classify it as:

- behavior that needs a focused test;
- error handling that can be triggered with mock HTTP or malformed fixtures;
- dead code that should be removed;
- live-server-only behavior that belongs behind `-m live`;
- defensive code that should stay uncovered only with a clear reason.

## Add Tests

- Prefer existing test files and fixtures.
- Assert behavior, not implementation trivia.
- For xarray objects, use `xarray.testing` helpers when comparing datasets or
  arrays.
- Preserve laziness assertions and exact request counts where relevant.
- Include error paths, malformed metadata, CoverageJSON edge cases, Dask/pickle
  behavior, and hook routing when those paths are touched.
- Do not add `pragma: no cover` to avoid testing reachable logic.

## Verify

Run focused tests first, then:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

Report before/after coverage and the behavior each new test protects.
