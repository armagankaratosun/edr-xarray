---
description: Address unresolved GitHub PR review comments and push fixes
agent: build
---

# Address Pull Request Comments

Use this when a PR has reviewer feedback that should be resolved in code, tests,
or docs.

## Inputs

Provide a PR number, or detect the current branch's open PR with `gh pr view`.

## Workflow

- Fetch unresolved review threads with `gh api graphql` so inline comments are
  included, then fetch review summaries and root-level comments.
- Read the full file context around each comment before changing anything.
- Classify each comment as actionable, already handled, ambiguous, or out of
  scope.
- Ask the user before making a product decision that is not clear from the
  comment or repository docs.
- For each actionable comment:
  - fix the underlying behavior rather than hiding the symptom;
  - add or update focused tests when the comment identifies a behavior gap;
  - update README, plans, examples, or changelog when public behavior changes.
- Run focused tests for touched behavior, then the full local gate:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy --strict src/edr_xarray
uv run pyright
uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"
```

- Commit with a clear message, push, and watch PR checks with `gh pr checks`.
- Report each reviewer comment and the action taken.
