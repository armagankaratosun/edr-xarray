## Summary

<!-- What changed and why? -->

## Checks

- [ ] `uv run ruff check src tests`
- [ ] `uv run ruff format --check src tests`
- [ ] `uv run mypy --strict src/edr_xarray`
- [ ] `uv run pyright`
- [ ] `uv run pytest --cov=src/edr_xarray --cov-fail-under=95 -v -m "not live"`

## Behavior Review

- [ ] Lazy open semantics and request counts are preserved or intentionally updated.
- [ ] xarray still owns `chunks` and `cache`.
- [ ] `EdrDataStore` hook routing is preserved for external cube behavior.
- [ ] Dask and pickle behavior were tested or are unaffected.
- [ ] Public behavior changes are reflected in README, examples, plans, or changelog.
- [ ] Live tests were run if this needs a real EDR server.
