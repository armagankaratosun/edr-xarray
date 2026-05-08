"""Pickle round-trip and Dask compatibility tests for edr-xarray Dataset.

Dask tests are skipped if dask is not installed.
"""

# pyright: reportMissingImports=false

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
from pytest_httpserver import HTTPServer

META_BASIC: dict[str, Any] = json.loads(
    Path("tests/data/collection_metadata_basic.json").read_text()
)
COV_3D: dict[str, Any] = json.loads(Path("tests/data/cov_grid_3d.json").read_text())


def _setup(httpserver: HTTPServer) -> str:
    """Register metadata + probe + flexible cube endpoint. Return collection URL."""
    meta = copy.deepcopy(META_BASIC)
    meta["id"] = "test"
    cube_href = httpserver.url_for("/collections/test/cube")
    meta["data_queries"]["cube"]["link"]["href"] = cube_href
    httpserver.expect_ordered_request("/collections/test").respond_with_json(meta)
    httpserver.expect_ordered_request("/collections/test/cube").respond_with_json(COV_3D)
    httpserver.expect_request("/collections/test/cube").respond_with_json(COV_3D)
    return httpserver.url_for("/collections/test")


def test_pickle_dataset_roundtrip(httpserver: HTTPServer) -> None:
    """Pickle/unpickle a Dataset; the unpickled version can still fetch data."""
    url = _setup(httpserver)
    ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"])

    blob = pickle.dumps(ds)
    ds2 = pickle.loads(blob)

    assert ds2 is not ds
    assert "temperature" in ds2.data_vars
    assert ds2["temperature"].shape == ds["temperature"].shape

    arr = ds2["temperature"].values
    assert arr.shape == ds["temperature"].shape
    assert np.isfinite(arr).any()


def test_pickle_preserves_store_state(httpserver: HTTPServer) -> None:
    """After pickle round-trip the store's collection_url and transport are restored."""
    from edr_xarray.array import EdrBackendArray
    from edr_xarray.transport import Transport

    url = _setup(httpserver)
    # cache=False keeps the lazy chain inspectable without a MemoryCachedArray wrapper.
    ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"], cache=False)

    blob = pickle.dumps(ds)
    ds2 = pickle.loads(blob)

    arr: Any = ds2["temperature"].variable._data
    while hasattr(arr, "array") and not isinstance(arr, EdrBackendArray):
        arr = arr.array

    assert isinstance(arr, EdrBackendArray)
    from typing import cast as _cast

    from edr_xarray.store import EdrDataStore as _StoreImpl

    concrete_store = _cast(_StoreImpl, arr._store)
    assert concrete_store.collection_url == url
    assert isinstance(concrete_store._transport, Transport)


def test_pickle_array_roundtrip(httpserver: HTTPServer) -> None:
    """Pickle/unpickle a lazy backend array directly using a real EdrDataStore."""
    from edr_xarray.array import EdrBackendArray
    from edr_xarray.indexer import AxisInfo
    from edr_xarray.store import EdrDataStore

    url = _setup(httpserver)
    store = EdrDataStore(collection_url=url)

    axes = (
        AxisInfo(
            name="t",
            values=np.array(["2025-01-01T00:00:00"], dtype="datetime64[ns]"),
            kind="t",
        ),
        AxisInfo(name="y", values=np.array([40.0, 41.0]), kind="y"),
        AxisInfo(name="x", values=np.array([10.0, 11.0]), kind="x"),
    )

    arr = EdrBackendArray(
        store=store,
        cube_url=httpserver.url_for("/collections/test/cube"),
        parameter_id="temperature",
        axes=axes,
        shape=(1, 2, 2),
        dtype=np.dtype("float64"),
    )

    blob = pickle.dumps(arr)
    arr2 = pickle.loads(blob)

    assert arr2 is not arr
    assert arr2.shape == arr.shape
    assert arr2.dtype == arr.dtype
    assert arr2._cube_url == arr._cube_url
    assert arr2._parameter_id == arr._parameter_id
    assert tuple(a.kind for a in arr2._axes) == ("t", "y", "x")


def test_dask_compute_via_chunks(httpserver: HTTPServer) -> None:
    """Dataset opened with chunks= integrates with Dask for out-of-core compute."""
    pytest.importorskip("dask", reason="dask not installed")
    import dask.array as da

    url = _setup(httpserver)
    ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"], chunks={"t": 1})

    temp = ds["temperature"]
    assert isinstance(temp.data, da.Array)

    result = temp.compute()
    assert result.shape == (1, 2, 2)
    assert np.isfinite(result.values).any()
