
## F4 Scope Fidelity Check - 2026-05-08
- Plan checkbox command returned 18 checked / 17 unchecked; implementation task 1 remains unchecked, so implementation tasks are 18/19 complete in plan state.
- Source modules present: 13/13 including py.typed.
- Test files present: 17/17.
- Boundary grep found src/edr_xarray/store.py docstring mention of xarray-firecube; no refresh/cube-series/localhost behavior found, but strict grep is not clean.
- Non-cube query type grep: clean.
- GeoJSON/NetCDF grep: clean.
- Entry point, Apache-2.0 license, CI uv workflow, and 19 implementation commits present.
- Verdict: REJECT until plan T1 is checked and source boundary grep is clean.

## F4 Scope Fidelity Check Re-run - 2026-05-08
- Requested re-run after ruff formatting and store.py docstring cleanup: boundary grep is now clean for firecube, non-cube query types, and GeoJSON/NetCDF.
- Plan completion still reports 18 checked / 1 unchecked; unchecked implementation task is T1 Project scaffolding.
- Source module count reports 12 under `src/edr_xarray/*.py` while the expected count is 13; only 12 Python modules are present.
- Test files remain 17/17, entry point is correct, LICENSE first line is `Apache License`, CI uv workflow is present.
- Verdict remains REJECT due to plan checkbox count and source module count mismatches.

## Examples notebooks task — 2026-05-08
- Created `examples/` with README.md + 6 self-contained `.ipynb` notebooks.
- Mock server pattern: stdlib-only `http.server.HTTPServer` in a daemon thread, `_routes` dict mutated post-server-start to inject the live port into the metadata `cube.link.href` (chicken-and-egg between port and metadata href solved by mutating shared dict reference).
- Probe vs metadata_only difference: probe yields full-resolution coord arrays from the cube response; metadata_only emits 2-point arrays from `extent.spatial.bbox` corners (verified: probe → 3×3×3, metadata_only → 3×2×2 with same temporal.values).
- `EdrDataStore` can be used directly via `store.build_dataset()` — no entrypoint registration needed for subclass demos.
- `Dataset.dims` triggers a `FutureWarning` from xarray (`set` vs mapping); upstream-only and not actionable.
- Notebooks exercise discovery probe + cube fetch + indexer translation end-to-end against the mock; serves as additional regression coverage independent of the pytest suite.
