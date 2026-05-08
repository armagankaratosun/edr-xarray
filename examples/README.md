# edr-xarray examples

Jupyter notebooks demonstrating the `edr-xarray` library against a real
EDR collection URL. Set `collection_url` in each notebook to point at your
own server.

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
PyCharm, etc. Update `collection_url` before running a notebook.

## Notes

- The notebooks ship with empty `outputs` — re-execute cells in order
  to see live output.
- No new dependencies are introduced beyond what `pyproject.toml` already
  requires (`xarray`, `httpx`, `numpy`, plus the optional `dask` for the
  Dask notebook).
- These examples are not part of the test suite and are not enforced by
  `ruff` or `mypy`; treat them as user-facing documentation.
