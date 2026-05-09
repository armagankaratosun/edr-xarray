---
description: Run a strictness-graded quality review pass over the repo or changed area
agent: build
---

# Further Quality Pass

Use this after implementation or before a PR when the code needs another review
cycle. If a pass number is supplied, increase strictness as the number rises.

## Foundation Checks

- Simplify unnecessary complexity.
- Improve names that hide domain meaning.
- Remove duplication and stale comments.
- Check for duplicated sources of truth: version, defaults, supported discovery
  modes, hook names, query parameter names, and documented limitations.
- Run format, lint, type, and focused tests.

## Hardening Checks

- Audit edge cases and error messages.
- Confirm no eager data fetches were introduced.
- Confirm xarray owns `chunks` and `cache`.
- Confirm hook routing still covers external cube traffic.
- Confirm pickle/Dask behavior if backend arrays, stores, transport, or encoding
  changed.
- Confirm public docs and examples match behavior.

## Polish Checks

- Every public function, class, option, and hook has useful documentation.
- Every intended error path has a test or a documented reason it cannot be
  tested offline.
- Similar behavior is handled consistently across modules.
- No unnecessary allocations, copies, or conversions were introduced in hot
  indexing/fetch paths.

## Verify

Run focused tests first, then:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

Summarize findings, fixes, remaining risks, and recommended next focus.
