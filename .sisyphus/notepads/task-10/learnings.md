## 2026-05-08
- Discovery datetime values from metadata need trailing `Z` stripped before `np.datetime64(..., 'ns')`; pytest treats NumPy timezone warnings as errors.
- `pytest-cov --cov=src/edr_xarray/discovery` does not resolve this single-file module here; `--cov=edr_xarray.discovery` produces the expected per-module coverage report.
