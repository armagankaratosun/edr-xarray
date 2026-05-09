"""Opt-in live integration tests against a running EDR server.

Run with:
    EDR_LIVE_URL=http://localhost:8000 uv run pytest -m live

Optionally set EDR_LIVE_COLLECTION to the collection ID to open
(defaults to the first collection advertised by the server).

Skipped automatically when EDR_LIVE_URL is not set or server is unreachable.
"""

from __future__ import annotations

import os

import httpx
import pytest
import xarray as xr


def _base_url() -> str:
    if url := os.environ.get("EDR_LIVE_URL"):
        return url
    pytest.skip("EDR_LIVE_URL is not set")


def _collection_id(server_url: str) -> str:
    """Return the collection ID to test against.

    Uses EDR_LIVE_COLLECTION env var if set; otherwise picks the first
    collection advertised by the server's /collections endpoint.
    """
    if col := os.environ.get("EDR_LIVE_COLLECTION"):
        return col
    try:
        resp = httpx.get(f"{server_url}/collections", timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"could not list collections from {server_url}: {exc}")
    collections = resp.json().get("collections", [])
    if not collections:
        pytest.skip("server advertises no collections")
    return str(collections[0]["id"])


@pytest.fixture(scope="module")
def edr_server() -> str:
    """Return live EDR server base URL; skip if unreachable."""
    url = _base_url()
    try:
        response = httpx.get(f"{url}/conformance", timeout=2.0)
        response.raise_for_status()
    except Exception as exc:
        pytest.skip(f"EDR server unreachable at {url}: {exc}")
    return url


@pytest.mark.live
def test_live_open_collection(edr_server: str) -> None:
    """Open the first advertised collection and verify the dataset structure."""
    col_id = _collection_id(edr_server)
    ds = xr.open_dataset(
        f"{edr_server}/collections/{col_id}",
        engine="edr",
    )
    assert len(ds.dims) > 0, "Dataset should have at least one dimension"
    assert len(ds.data_vars) > 0, "Dataset should have at least one variable"


@pytest.mark.live
def test_live_fetch_values(edr_server: str) -> None:
    """Open a collection and trigger a data fetch via .values."""
    col_id = _collection_id(edr_server)
    ds = xr.open_dataset(
        f"{edr_server}/collections/{col_id}",
        engine="edr",
    )
    var_name = next(iter(ds.data_vars))
    arr = ds[var_name].values
    assert arr is not None
    assert arr.size > 0


@pytest.mark.live
def test_live_spatial_subset(edr_server: str) -> None:
    """Open a collection with a spatial bbox subset."""
    col_id = _collection_id(edr_server)
    ds = xr.open_dataset(
        f"{edr_server}/collections/{col_id}",
        engine="edr",
        bbox=(10.0, 40.0, 11.0, 41.0),
    )
    assert len(ds.dims) > 0

    var_name = next(iter(ds.data_vars))
    arr = ds[var_name].values
    assert arr is not None
    assert arr.size > 0
