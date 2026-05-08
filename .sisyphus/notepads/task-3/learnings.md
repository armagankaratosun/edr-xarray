# Task 3 — Learnings

## Coverage tooling
- `--cov=src/edr_xarray/coveragejson` (path form) silently failed to collect data; pytest-cov interpreted it as a package name. Use the dotted module form `--cov=edr_xarray.coveragejson` (works) OR the directory form `--cov=src/edr_xarray`. The path-style spec in the task description is unreliable — always re-verify in the printed report.

## frozen dataclasses + numpy arrays
- `@dataclass(frozen=True, eq=False)` is the cleanest way to embed `np.ndarray` fields without triggering `ValueError: The truth value of an array is ambiguous`. Disabling auto `__eq__` falls back to identity comparison; tests use `np.allclose` / element-wise comparison directly.

## numpy generic typing under `disallow_any_generics = true`
- Despite `mypy --strict + disallow_any_generics = true` in this project, plain `np.ndarray` (no parameters) does NOT raise a mypy error in the current numpy stubs version. The `# type: ignore[type-arg]` was UNUSED, and mypy flagged it. Keep ndarray unparametrized — leaner.

## ISO-time → datetime64
- The pattern `np.datetime64(s.rstrip("Z"), "ns")` is the right call for CoverageJSON time strings; numpy 2.x rejects the trailing `Z` directly.

## ruff D-rule docstrings
- The project's ruff config selects `D` (pydocstyle) which requires docstrings on every public function/module. Tests must have docstrings on every test function or `ruff check` fails. The hook complaining about docstrings is overridden by this project requirement.
