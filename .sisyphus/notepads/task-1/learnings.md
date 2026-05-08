Observed that `uv` emits a deprecation warning for `[tool.uv].dev-dependencies`; the scaffold still works, but future tasks may move dev requirements to `dependency-groups.dev`.
Ruff enforces docstrings on `__init__` and `__str__` under the current lint set, so small exception classes need explicit method docstrings to stay clean.
Pyright missing-import reports for `src`-layout tests may need an explicit suppression when the workspace hasn't been configured for the package path yet.
## Task 6: pytest-httpserver scaffolding
- Keep `tests/conftest.py` free of `edr_xarray` imports so fixtures stay pure and reusable.
- `httpserver.url_for(...)` is the right way to inject absolute URLs into JSON metadata fixtures.
- `pytest --fixtures tests/` is a useful sanity check for confirming helper functions appear as plain functions, not fixtures.
