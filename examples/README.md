# edr-xarray examples

Three short Jupyter notebooks demonstrating real `edr-xarray` usage against
a live EDR server.  Set `server` in the first code cell of each notebook.

| Notebook | What it shows |
|---|---|
| [01_quickstart.ipynb](01_quickstart.ipynb) | Discover collections, open one, inspect. |
| [02_fwi_map.ipynb](02_fwi_map.ipynb) | Single-day Fire Weather Index map over Spain with the EFFIS 6-class colormap. |
| [03_fwi_animation.ipynb](03_fwi_animation.ipynb) | Multi-day FWI animation with a built-in date slider (plotly). |

## Running

```bash
uv sync
uv run jupyter lab examples/
```

Or open any notebook in your editor of choice.  The first cell installs
the package in editable mode from the local repo, so no PyPI release is
needed.
