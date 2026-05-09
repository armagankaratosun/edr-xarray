---
description: Run pre-flight checks and prepare a pull request
agent: build
---

# Prepare Pull Request

Use this when implementation is complete and the branch should be made ready for
review.

## Pre-Flight

Run all required checks:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

If docs, examples, packaging, notebooks, or releases changed, run the relevant
extra checks such as `uv build` or notebook smoke checks.

## Review The Diff

- Stage only intentional source, tests, docs, prompt, plan, config, and lockfile
  changes.
- Do not stage `.venv/`, caches, build artifacts, notebook checkpoints, or local
  scratch files.
- Confirm public behavior changes have README/docs/tests/changelog updates.
- Confirm laziness, hook routing, Dask/pickle, and version-source impacts have
  been considered.

## PR Body

Use a concise body with:

- Summary
- Tests
- Public API or behavior changes
- Follow-ups or known risks

Push the branch, open the PR, and report the URL.
