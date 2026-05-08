## 2026-05-08

- Used `dataclasses.replace()` for parameter filtering to preserve frozen `CollectionMetadata` semantics.
- Kept `xr.Coordinates(coord_vars, indexes={})` to avoid implicit index creation while assembling the dataset.
