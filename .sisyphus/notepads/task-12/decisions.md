## Task 12

- Used a type-checking-only Protocol for the store hooks because `EdrDataStore` is scheduled for a later task; this keeps runtime duck typing and strict mypy clean without importing a missing module.
- Preserved hook routing for all cube traffic: `_translate_indexer`, `_request`, and `_parse_coveragejson` are the only store integration points in `EdrBackendArray`.
