# Task 3 — Decisions

## Trust JSON-typed inputs in helper paths
After Python's `json.loads` we have str/int/float/list/dict/None — not arbitrary objects. Defensive `isinstance` chains in `_parse_parameter` and `_parse_range` were creating uncovered branch combinatorics that pushed coverage below 95%. Replaced with:
- `_nested_str(spec, *path)` helper that walks dicts and returns a final string or None.
- Direct `spec["axisNames"]` / `spec["shape"]` / `spec["values"]` lookups in `_parse_range` — `KeyError` on a malformed payload is acceptable since these are required fields per the CoverageJSON spec.

This kept the spec-mandated validations (TiledNdArray rejection, null-in-integer rejection, value-count vs shape product, axisNames consistency, shape consistency, axis-length vs shape match) and dropped over-engineering that wasn't in the task contract.

## Dataclasses with `eq=False`
`Axis` and `CoverageData` carry numpy arrays so we set `eq=False` rather than inventing custom `__eq__`. Identity comparison is fine for our use case (parsed objects are constructed once per response and not deduplicated by value).
