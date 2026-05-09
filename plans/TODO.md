# TODO

Accepted backlog items for future implementation:

- Validate `discovery` mode at the xarray entrypoint instead of relying on a
  later fallback path.
- Document edge-case semantics for empty axes, scalar selections, unsupported
  CoverageJSON shapes, and server error responses.
- Add a small docs area if README and examples stop being enough.
- Consider CI enforcement for Pyright and docs/notebook smoke checks after the
  local stricter workflow settles.
- Review xarray internal imports during xarray upgrades and add compatibility
  notes when needed.
