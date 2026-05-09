---
description: Verify docs, examples, and README claims against the codebase
agent: build
---

# Documentation Fact-Check

Use this before releases or after API, behavior, docs, or example changes.

## Scope

If arguments are supplied, check only those files. Otherwise check `README.md`,
`CONTRIBUTING.md`, `plans/*.md`, `.prompts/*.md`, and `examples/README.md`.

## Checks

- Verify code identifiers, option names, hook names, command names, and defaults
  against the source.
- Verify `xr.open_dataset(..., engine="edr")` examples do not imply eager data
  loading. Fetch boundaries should be explicit through `.values`, `.load()`, or
  `.compute()`.
- Verify all documented `EdrDataStore` hooks exist and route cube traffic.
- Verify command examples match the actual `pyproject.toml` tooling.
- For Python snippets that are self-contained and do not require live EDR
  credentials, run them in a temporary file with `uv run python`.
- For notebooks under `examples/`, smoke-check JSON metadata and imports when
  possible. Do not run live server cells unless the user provides an EDR
  endpoint.
- Verify release/version claims against `VERSION`, `pyproject.toml`, package
  metadata, and `edr_xarray.__version__`.

## Report

For each finding, include:

```text
[ERROR|STALE|DRIFT] path:line - summary
Docs say: ...
Code says: ...
Suggested fix: ...
```

Do not silently edit factual claims unless the user asked for fixes. If fixes
are requested, update tests/docs together and run the relevant checks.
