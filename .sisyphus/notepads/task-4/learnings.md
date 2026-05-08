# Task 4 — metadata parser learnings

- Pure parser pattern: all functions return frozen dataclasses, no I/O,
  no logging, no globals. Validation errors raise `EdrMetadataError`
  with the missing field name in the message.
- Coverage target uses the import path: `--cov=edr_xarray.metadata`,
  not the filesystem path `--cov=src/edr_xarray/metadata` (the latter
  emits "module not imported" warnings and yields no data).
- ruff `D403` (first-word capitalization) applies to test docstrings
  too — capitalize "Bbox", "Cube", "Payload", etc.
- ruff `ANN401` forbids `typing.Any` parameters/returns; for tiny
  helpers like `_require(value, field)` it is cleaner to inline the
  None-check than to keep an `Any`-typed wrapper.
- For `cube_url` the simple rule "href ends with /cube → splice
  /instances/<id>/cube before the suffix" matches the EDR 1.1 URL
  shape; non-standard hrefs raise so subclasses can override.
- `urljoin(base.rstrip("/") + "/", href.lstrip("/"))` is the safe form
  to resolve relative cube hrefs against a base URL.
- `dataclasses.FrozenInstanceError` is the precise exception to assert
  in frozen-dataclass mutation tests (avoid the bare `Exception`).
