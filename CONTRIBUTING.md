# Contributing

Thanks for working on `edr-xarray`. This package is alpha software, so the bar is
not "preserve every accidental behavior"; it is "make the behavior simpler,
tested, documented, and useful to xarray users."

Read `AGENTS.md`, `plans/DESIGN.md`, and `plans/STYLE.md` before changing backend
or public behavior.

## Setup

```bash
uv sync --all-groups
```

## Local Checks

Run focused tests for the code you touched, then run the full local gate:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

Use live tests only when you have a server configured:

```bash
EDR_LIVE_URL=http://localhost:8000 uv run pytest -m live
```

## Development Rules

- Preserve lazy loading. Opening a dataset should not fetch user data.
- Preserve xarray ownership of `chunks` and `cache`.
- Route external cube behavior through the documented `EdrDataStore` hooks.
- Keep parser and encoder helpers pure unless the design doc is updated.
- Add or update tests for behavior changes, including error paths.
- Update README, examples, plans, or changelog when public behavior changes.
- Avoid broad `# noqa`, `# type: ignore`, warning filters, or skipped tests. Fix
  the root cause, or use a narrow suppression with a reason.

## Releases

`VERSION` is the canonical version. Release tags use `X.Y.Z`, not `vX.Y.Z`.
Before releasing, run the full local gate and `uv build`, update
`CHANGELOG.md`, and confirm package metadata matches `VERSION`.
