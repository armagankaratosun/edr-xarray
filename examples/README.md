# edr-xarray examples

Self-contained Jupyter notebooks demonstrating the `edr-xarray` library.
Every notebook spins up its own in-process mock EDR server using only
Python's standard library — **no live server is required** to run any
example.

## Notebooks

| Notebook | What it shows |
|---|---|
| [01_basic_usage.ipynb](01_basic_usage.ipynb) | Open a collection, inspect dims/vars/attrs, load values lazily. |
| [02_subsetting.ipynb](02_subsetting.ipynb) | Spatial (`bbox`), temporal (`datetime`), vertical (`z`), and parameter subsetting. |
| [03_discovery_modes.ipynb](03_discovery_modes.ipynb) | Compare `probe`, `metadata_only`, and `strict` axis discovery. |
| [04_authentication.ipynb](04_authentication.ipynb) | Inject API keys, bearer tokens, custom timeouts, and dynamic-auth subclasses. |
| [05_dask_integration.ipynb](05_dask_integration.ipynb) | Chunked lazy loading with Dask, reductions, and pickle round-trips. |
| [06_subclassing.ipynb](06_subclassing.ipynb) | Override all seven `EdrDataStore` hooks for custom behavior. |

## Running

```bash
uv sync
uv run jupyter lab examples/
```

Or open any notebook in your editor of choice — VS Code, JupyterLab,
PyCharm, etc. The mock server is started inside the notebook itself,
so each notebook is independently runnable in any order.

## How the mock works

Each notebook embeds a tiny `http.server.HTTPServer` on `127.0.0.1` with
a randomly chosen port. The server serves two routes:

- `GET /collections/demo_collection` — returns OGC EDR collection metadata.
- `GET /collections/demo_collection/cube` — returns a CoverageJSON document.

Query parameters are intentionally ignored by the mock so that any
`bbox`, `datetime`, `z`, or `parameter-name` filter is accepted. The
server runs in a background daemon thread and is shut down at the end
of each notebook.

## Notes

- The notebooks ship with empty `outputs` — re-execute cells in order
  to see live output.
- No new dependencies are introduced beyond what `pyproject.toml` already
  requires (`xarray`, `httpx`, `numpy`, plus the optional `dask` for the
  Dask notebook).
- These examples are not part of the test suite and are not enforced by
  `ruff` or `mypy`; treat them as user-facing documentation.
