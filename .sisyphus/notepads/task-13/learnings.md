## 2026-05-08

- `EdrDataStore` should pass every external operation through hooks so subclasses can override metadata parsing, format negotiation, URL construction, coverage parsing, index translation, and axis discovery.
- `build_dataset()` can remain lazy by only creating `EdrBackendArray` instances; shape/dims come from discovered axes, while actual cube data fetches wait until `.values`/indexing.
- Coverage evidence for a single module needs `--cov=edr_xarray.store`; `--cov=src/edr_xarray/store` is treated as an unimported module by pytest-cov in this environment.
