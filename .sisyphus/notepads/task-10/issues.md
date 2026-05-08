## 2026-05-08
- Initial required coverage command using `--cov=src/edr_xarray/discovery` emitted no report because pytest-cov treated it as an import target/path that does not exist without `.py`.
