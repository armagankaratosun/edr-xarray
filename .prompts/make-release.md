---
description: Cut a new edr-xarray release
agent: build
---

# Make Release

Use this to prepare a release. Tags use plain `X.Y.Z` without a leading `v`.

## Inputs

Provide the target version as an argument. If omitted, propose the next minor
version from `VERSION` and ask before changing files.

## Pre-Release Checks

- Working tree must be clean except for intentional release edits.
- Confirm local branch is pushed and up to date with the release branch.
- Run:

```bash
uv sync --all-groups
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
uv build
```

Stop and report any failure.

## Version Bump

`VERSION` is canonical. Update all release-facing locations to match:

- `VERSION`
- `CHANGELOG.md`
- any README/docs/examples mentioning the released version

Package metadata reads `VERSION` dynamically. Verify with:

```bash
uv build
uv run python -c "import importlib.metadata as m; import edr_xarray; print(m.version('edr-xarray'), edr_xarray.__version__)"
```

## Changelog

Add a release entry dated with the release date. Group changes as Added,
Changed, Fixed, Removed, and Documentation when useful.

## Tag And Publish

- Commit release edits with `chore: release X.Y.Z`.
- Tag `X.Y.Z`.
- Push the branch and tag.
- Build and inspect sdist/wheel artifacts before publishing.
- After publication, smoke test in a fresh environment with:

```bash
python -m venv /tmp/edr-xarray-smoke
/tmp/edr-xarray-smoke/bin/python -m pip install edr-xarray==X.Y.Z
/tmp/edr-xarray-smoke/bin/python -c "import xarray as xr; print('edr' in xr.backends.list_engines())"
```
