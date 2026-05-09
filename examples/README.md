# edr-xarray examples

Three short Jupyter notebooks demonstrate the core `edr-xarray` workflow
against a live EDR server. The notebooks use `https://edr.example.com` as a
placeholder. Each notebook lists the collections or variables it sees, then
uses explicit `collection_id`, `variable`, and `indexer` cells for you to edit.

| Notebook | What it shows |
|---|---|
| [01_quickstart.ipynb](01_quickstart.ipynb) | Open a live collection lazily, inspect it, and fetch one value. |
| [02_indexing_and_fetching.ipynb](02_indexing_and_fetching.ipynb) | Use xarray indexing, EDR filters, `.load()`, and a small plot. |
| [03_backend_options.ipynb](03_backend_options.ipynb) | Compare discovery modes, caller-owned HTTP clients, and Dask chunks. |

## Running

```bash
uv sync
uv run --with jupyterlab jupyter lab examples/
```

Or open any notebook in your editor of choice. The first cell installs
the package in editable mode from the local repo, so no PyPI release is
needed.
