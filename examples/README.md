# edr-xarray examples

Two short Jupyter notebooks demonstrating real `edr-xarray` usage against
a live EDR server.  Set `server` in the first code cell of each notebook.

| Notebook | What it shows |
|---|---|
| [01_basic_usage.ipynb](01_basic_usage.ipynb) | Discover collections, open one, inspect, fetch values. |
| [02_subset_and_plot.ipynb](02_subset_and_plot.ipynb) | Subset to a bounding box and plot the result. |

## Running

```bash
uv sync
uv run jupyter lab examples/
```

Or open any notebook in your editor of choice.  The first cell installs
the package in editable mode from the local repo, so no PyPI release is
needed.
