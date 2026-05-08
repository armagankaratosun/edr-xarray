2026-05-08: CI workflow should use `astral-sh/setup-uv@v3` with `enable-cache: true` and `uv sync --frozen --all-groups` for this repo.
2026-05-08: `uv run ruff format --check src tests` was initially failing; formatting the repo made ruff, mypy, and pytest all pass cleanly.
