"""Opt-in live integration tests against a running firecube EDR server.

Run with:
    EDR_LIVE_URL=http://localhost:8000 uv run pytest -m live

Skipped automatically when EDR_LIVE_URL is not set or server is unreachable.
"""

from __future__ import annotations

import os

import httpx
import pytest
import xarray as xr


def _base_url() -> str:
    return os.environ.get("EDR_LIVE_URL", "http://localhost:8000")


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
def test_live_firecube_open_msg_frm(edr_server: str) -> None:
    """Open the msg_frm collection from firecube and fetch data."""
    ds = xr.open_dataset(
        f"{edr_server}/collections/msg_frm",
        engine="edr",
        instance="f024",
    )
    assert len(ds.dims) > 0, "Dataset should have at least one dimension"
    assert len(ds.data_vars) > 0, "Dataset should have at least one variable"

    var_name = next(iter(ds.data_vars))
    arr = ds[var_name].values
    assert arr is not None


@pytest.mark.live
def test_live_firecube_subset_query(edr_server: str) -> None:
    """Open msg_frm with a spatial bbox subset."""
    ds = xr.open_dataset(
        f"{edr_server}/collections/msg_frm",
        engine="edr",
        instance="f024",
        bbox=(10.0, 40.0, 11.0, 41.0),
    )
    assert len(ds.dims) > 0

    var_name = next(iter(ds.data_vars))
    full_arr = ds[var_name].values
    assert full_arr is not None
    assert full_arr.size > 0
