---
description: Audit and harden edge-case behavior across the Python xarray backend
agent: build
---

# Improve Edge Cases

Use this for systematic hardening of metadata parsing, CoverageJSON parsing,
index translation, transport behavior, xarray integration, and Dask workflows.

## What To Look For

- Empty or minimal metadata, missing fields, unknown axes, multiple bboxes, and
  unsupported EDR query shapes.
- CoverageJSON with nulls, NaN, Inf, integer ranges with nulls, mismatched
  shapes, inconsistent `axisNames`, unsupported domains, and non-object JSON.
- Scalar and slice indexing, negative indices, dimension-dropping selections,
  full slices, and label selections that become narrow EDR query parameters.
- Lazy behavior regressions: extra requests on open, duplicate probe requests,
  or eager cube fetches from shape/dtype inspection.
- Dask and pickle behavior after session restoration.
- Transport errors with status code, URL, problem details, non-JSON bodies, and
  network exceptions.
- Unicode parameter names and metadata strings when the EDR/CoverageJSON specs
  allow them.

## Process

- State the intended semantics before changing behavior.
- Ask the user when a behavior choice is product policy rather than a bug.
- Add focused tests before or alongside fixes.
- Document public edge-case behavior in README, plans, examples, or changelog.
- Prefer explicit `EdrMetadataError`, `EdrCoverageJsonError`,
  `EdrUnsupportedFeatureError`, or `EdrServerError` over silent fallbacks.

## Verify

Run the focused tests that cover the edge case, then the full local gate.
