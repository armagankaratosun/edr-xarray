# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog, and this project uses SemVer-style
`MAJOR.MINOR.PATCH` versions. Tags do not use a leading `v`.

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
