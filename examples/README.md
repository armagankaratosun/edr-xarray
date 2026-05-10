# edr-xarray examples

Three short Jupyter notebooks demonstrate the core `edr-xarray` workflow
against a live EDR server. The notebooks use `https://edr.example.com` as a
placeholder. Each notebook lists the collections or variables it sees, then
uses explicit `collection_id`, `variable`, and `indexer` cells for you to edit.
For collections with long temporal axes, choose a bounded `datetime` window in
the `xr.open_dataset(...)` cell so the opened `ds.t` coordinate matches the
window you intend to fetch or plot.
For collections with forecast runs or versions, `03_backend_options.ipynb`
shows `instance=` opening: collection metadata is read first, selected instance
metadata defines the dataset, and data values remain lazy.

| Notebook | What it shows |
|---|---|
| [01_quickstart.ipynb](01_quickstart.ipynb) | Open a live collection lazily, inspect it, and fetch one value. |
| [02_indexing_and_fetching.ipynb](02_indexing_and_fetching.ipynb) | Use xarray indexing, EDR filters, `.load()`, and a small plot. |
| [03_backend_options.ipynb](03_backend_options.ipynb) | Compare discovery modes, instance metadata, caller-owned HTTP clients, and Dask chunks. |

## Running

```bash
uv sync
uv run --with jupyterlab jupyter lab examples/
```

Or open any notebook in your editor of choice. The first cell installs
the published package from PyPI, so the notebooks can run outside a local
source checkout.
