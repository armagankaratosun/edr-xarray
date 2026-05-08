Kept `.sisyphus/evidence/` gitignored while leaving `.sisyphus/` itself tracked for plans and notes.
## Task 6: test scaffolding decisions
- Kept cube/instances link helpers as plain functions because tests can call them directly with specific payloads.
- Used shared JSON files under `tests/data/` for deterministic fixture loading and easier negative-test reuse.
