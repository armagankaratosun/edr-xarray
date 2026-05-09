# Motivation

`edr-xarray` makes OGC API - Environmental Data Retrieval data feel native to
xarray users. A collection URL can be opened with `xr.open_dataset(...,
engine="edr")`, inspected as a normal `Dataset`, and loaded lazily only when the
user asks for values.

The package exists to keep the EDR-specific parts small and explicit:

- translate collection metadata and CoverageJSON into xarray variables,
  coordinates, attributes, and lazy backend arrays;
- keep network access predictable and testable;
- expose server-specific customization through a narrow subclass hook surface;
- integrate cleanly with Dask and xarray's chunking model without inventing a
  second execution engine.

The project is alpha software. We prefer a simple, correct design over preserving
accidental behavior. Breaking changes are acceptable before 1.0 when tests and
documentation move with the behavior.
