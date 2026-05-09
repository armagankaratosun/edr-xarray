# Coding Style

Follow Pythonic PEP 8 and PEP 484 style, enforced by Ruff, mypy, and Pyright.
When in doubt, match the existing module's shape.

## Principles

1. Preserve lazy xarray behavior.
2. Keep module boundaries deep: expose small APIs, hide protocol and parsing
   complexity behind focused helpers.
3. Keep pure helpers pure.
4. Prefer explicit errors over silent coercion or surprising fallbacks.
5. Favor simple code over clever abstractions.

## Python

- Use `from __future__ import annotations`.
- Prefer `collections.abc` types for inputs and concrete return types for
  outputs.
- Use `object` or a small `Protocol` instead of `Any` when the contract can be
  stated precisely.
- Use frozen dataclasses for immutable parsed metadata records.
- Keep public APIs annotation-clean because the package ships `py.typed`.
- Do not add broad `# type: ignore`, `# noqa`, or warning filters. Narrow them
  with a reason when they are truly semantic.

## xarray

- Use `BackendEntrypoint`, `BackendArray`, `LazilyIndexedArray`, and
  `explicit_indexing_adapter()` according to xarray's backend contract.
- Put EDR-specific indexing in `_translate_indexer`; keep HTTP fetch and
  CoverageJSON parsing routed through store hooks.
- Use `xarray.testing` helpers for Dataset/DataArray comparisons.
- Do not imply eager loading in examples or docs.
- Keep user-facing examples as notebooks in `examples/`; avoid duplicate Python
  script examples for the same workflows.

## Design Patterns

Use composition first. GoF names such as Adapter, Strategy, or Facade are useful
only when they clarify an existing role in the code. Do not introduce a pattern
class hierarchy where a function, dataclass, or protocol is simpler.

## Comments

Explain why a constraint exists, what invariant is being preserved, or where a
third-party contract matters. Avoid comments that restate obvious code.
