## 2026-05-08

- `pyright` in tests needed `# pyright: reportMissingImports=false` because the src layout isn't wired for the editor in this repo.
- Coverage should target `edr_xarray.query`, not the file path string, to avoid "module was never imported" warnings.
- `ruff` D103/D202 can be satisfied cleanly with concise docstrings and no blank line after the docstring.
