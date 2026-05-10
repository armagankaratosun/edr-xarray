# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog, and this project uses SemVer-style
`MAJOR.MINOR.PATCH` versions. Tags do not use a leading `v`.

## [Unreleased]

## [0.1.2] - 2026-05-10

### Changed

- Probe discovery now uses open-time `datetime` and `z` filters when declaring
  xarray coordinates.
- Dataset coordinates now use normal xarray indexes, so `.sel()` works on
  declared dimensions.
- Abbreviated temporal metadata now defaults to the first instant unless
  `datetime=` is supplied.
- Empty `parameter_names` are rejected, and selected parameters drive probe
  discovery.
- Opening with `instance=` now fetches selected instance metadata and builds the
  dataset from that instance rather than collection-level metadata.
- FWI examples now open bounded time windows before fetching or plotting data.
- Package metadata now declares Python 3.11 and 3.12 support.

### Fixed

- Backend array reads now raise clear CoverageJSON errors when returned
  axes or shapes do not match the declared xarray dimensions.
- Spatial selections now handle descending latitude or longitude axes.
- Closing datasets after `drop_variables` now releases owned transports.
- Malformed metadata, malformed CoverageJSON, invalid sessions, and non-object
  JSON responses now raise package errors.
- CRS validation now checks both cube-level and collection-level CRS
  advertisements and accepts CRS84 aliases case-insensitively.
- Publish workflow now uploads only built distribution artifacts.
- Release publishing now runs the full quality gate first.

## [0.1.1] - 2026-05-10

### Changed

- Maintenance release with no runtime behavior changes from 0.1.0.

## [0.1.0] - 2026-05-09

### Added

- Initial lazy xarray backend for OGC API - EDR `/cubes` collections.
- CoverageJSON Grid parsing, xarray coordinate/data variable construction, Dask
  integration, and subclass extension hooks.
- Development guides, task prompts, planning docs, and release workflow notes.
- Jupyter notebook examples for lazy opening, xarray indexing, backend options,
  and Dask chunking against live EDR endpoints.
