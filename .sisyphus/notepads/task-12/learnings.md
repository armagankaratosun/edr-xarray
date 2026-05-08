## Task 12

- `xarray.core.indexing.explicit_indexing_adapter(..., IndexingSupport.BASIC, ...)` decomposes `OuterIndexer` selections into basic raw fetches plus NumPy-side indexing, so the backend array only needs basic `_raw_indexing_method` support.
- Coverage collection with pytest-cov must use the dotted module target `--cov=edr_xarray.array`; `--cov=src/edr_xarray/array` passes tests but records no coverage data.
