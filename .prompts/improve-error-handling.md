---
description: Audit exception paths and improve user-facing diagnostics
agent: build
---

# Improve Error Handling

Use this when errors are unclear, swallowed, over-broad, or under-tested.

## Checks

- No bare `except:` blocks.
- Broad `except Exception` blocks must wrap third-party parsing/transport
  boundaries and preserve the original cause with `raise ... from exc`.
- Error messages should include useful context such as collection URL, parameter
  name, axis name, status code, query shape, or unsupported feature.
- Do not convert specific exceptions into generic `ValueError` unless the public
  xarray entrypoint contract calls for it.
- Preserve the custom exception hierarchy exported from `edr_xarray`.
- Transport errors should preserve status code and URL where available.
- Metadata and CoverageJSON validation errors should fail early before partial
  datasets are exposed.

## Process

- Search source and tests for broad exception handling, assertions, and existing
  custom exceptions.
- Add failing tests for poor messages or missing causes.
- Fix root causes and keep exception types stable unless deliberately changing
  documented behavior.
- Update docs/examples if user-facing failure behavior changes.

## Verify

Run focused error tests, then the full local gate.
