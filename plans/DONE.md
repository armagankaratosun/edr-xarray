# Done

Notable completed work:

- Registered the `edr` xarray backend entrypoint.
- Implemented lazy dataset construction from EDR collection metadata.
- Added CoverageJSON Grid parsing for 2D, 3D, and 4D cubes.
- Added xarray indexer translation to EDR `bbox`, `datetime`, and `z` query
  parameters.
- Added subclass hooks for transport, metadata parsing, format negotiation, cube
  URL routing, CoverageJSON parsing, index translation, and axis discovery.
- Added strict Ruff, mypy, Pyright, pytest, and coverage tooling.
- Added Dask and pickle compatibility tests.
- Added agent, planning, prompt, and release guidance.
- Added core Jupyter notebook examples for lazy open, indexing/fetching, and
  backend options.
