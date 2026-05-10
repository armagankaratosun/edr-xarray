"""End-to-end integration tests for the complete edr-xarray open->compute flow."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
import xarray as xr
from pytest_httpserver import HTTPServer

from edr_xarray.errors import EdrCoverageJsonError

META_BASIC: dict[str, Any] = json.loads(
    Path("tests/data/collection_metadata_basic.json").read_text()
)
META_INSTANCES: dict[str, Any] = json.loads(
    Path("tests/data/collection_metadata_with_instances.json").read_text()
)
COV_3D: dict[str, Any] = json.loads(Path("tests/data/cov_grid_3d.json").read_text())
COV_4D: dict[str, Any] = json.loads(Path("tests/data/cov_grid_4d.json").read_text())


def _make_meta(httpserver: HTTPServer, collection_id: str) -> dict[str, Any]:
    meta = copy.deepcopy(META_BASIC)
    meta["id"] = collection_id
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for(
        f"/collections/{collection_id}/cube"
    )
    return meta


def _register_meta_and_probe(
    httpserver: HTTPServer,
    collection_id: str,
    cube_fixture: dict[str, Any] | None = None,
) -> str:
    meta = _make_meta(httpserver, collection_id)
    cube = cube_fixture if cube_fixture is not None else COV_3D
    httpserver.expect_ordered_request(
        f"/collections/{collection_id}", method="GET"
    ).respond_with_json(meta)
    httpserver.expect_ordered_request(
        f"/collections/{collection_id}/cube", method="GET"
    ).respond_with_json(cube)
    return httpserver.url_for(f"/collections/{collection_id}")


def test_open_dataset_then_select_then_compute_full_flow(httpserver: HTTPServer) -> None:
    """Full flow: open -> inspect dims/coords/attrs -> compute -> verify request log."""
    collection_url = _register_meta_and_probe(httpserver, "test_coll")
    httpserver.expect_request("/collections/test_coll/cube", method="GET").respond_with_json(COV_3D)

    ds = xr.open_dataset(collection_url, engine="edr", parameter_names=["temperature"])

    assert "temperature" in ds.data_vars
    assert set(ds.dims) == {"t", "y", "x"}
    assert ds.coords["x"].attrs["axis"] == "X"
    assert ds.coords["y"].attrs["axis"] == "Y"
    assert ds["temperature"].attrs.get("units") == "K"

    # open_dataset with discovery="probe" produces exactly 2 requests (metadata + probe).
    assert len(httpserver.log) == 2

    arr = ds["temperature"].values
    assert arr.shape == (1, 2, 2)
    assert np.isfinite(arr).any()

    # .values triggers exactly one additional HTTP fetch.
    assert len(httpserver.log) == 3

    ds.close()


def test_values_raise_when_fetch_shape_exceeds_declared_time_axis(
    httpserver: HTTPServer,
) -> None:
    """A server response with more times than declared fails through xarray .values."""
    collection_url = _register_meta_and_probe(httpserver, "shape_mismatch")
    mismatch = copy.deepcopy(COV_3D)
    mismatch["domain"]["axes"]["t"]["values"] = [
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
        "2025-01-03T00:00:00Z",
        "2025-01-04T00:00:00Z",
    ]
    mismatch["ranges"]["temperature"]["shape"] = [4, 2, 2]
    mismatch["ranges"]["temperature"]["values"] = [float(i) for i in range(16)]
    httpserver.expect_request("/collections/shape_mismatch/cube", method="GET").respond_with_json(
        mismatch
    )

    ds = xr.open_dataset(collection_url, engine="edr", parameter_names=["temperature"])
    try:
        with pytest.raises(EdrCoverageJsonError, match="xarray expected shape"):
            _ = ds["temperature"].values
    finally:
        ds.close()


def test_4d_cube_with_z(httpserver: HTTPServer) -> None:
    """4D cube with z axis is correctly discovered and exposed via probe."""
    meta = copy.deepcopy(META_BASIC)
    meta["id"] = "wx"
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for("/collections/wx/cube")

    httpserver.expect_ordered_request("/collections/wx", method="GET").respond_with_json(meta)
    httpserver.expect_ordered_request("/collections/wx/cube", method="GET").respond_with_json(
        COV_4D
    )
    httpserver.expect_request("/collections/wx/cube", method="GET").respond_with_json(COV_4D)

    collection_url = httpserver.url_for("/collections/wx")
    ds = xr.open_dataset(collection_url, engine="edr", parameter_names=["temperature"])

    assert "z" in ds.dims
    assert "temperature" in ds.data_vars
    assert ds["temperature"].dims == ("t", "z", "y", "x")
    assert ds.coords["z"].values.tolist() == [1000.0, 850.0, 500.0]

    arr = ds["temperature"].values
    assert arr.shape == (1, 3, 2, 2)
    assert np.isfinite(arr).all()

    ds.close()


def test_instance_kwarg_routes_through_instance_url(httpserver: HTTPServer) -> None:
    """instance= fetches instance metadata and routes cube requests through it."""
    meta = copy.deepcopy(META_INSTANCES)
    meta["id"] = "model"
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for("/collections/model/cube")
    meta["data_queries"]["instances"]["link"]["href"] = httpserver.url_for(
        "/collections/model/instances"
    )
    instance_meta = copy.deepcopy(meta)
    instance_meta["id"] = "f024"
    instance_meta["title"] = "Model f024"
    instance_meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for(
        "/collections/model/instances/f024/cube"
    )

    httpserver.expect_ordered_request("/collections/model", method="GET").respond_with_json(meta)
    httpserver.expect_ordered_request(
        "/collections/model/instances/f024", method="GET"
    ).respond_with_json(instance_meta)
    httpserver.expect_ordered_request(
        "/collections/model/instances/f024/cube", method="GET"
    ).respond_with_json(COV_3D)
    httpserver.expect_request(
        "/collections/model/instances/f024/cube", method="GET"
    ).respond_with_json(COV_3D)

    collection_url = httpserver.url_for("/collections/model")
    ds = xr.open_dataset(
        collection_url,
        engine="edr",
        instance="f024",
        parameter_names=["temperature"],
    )

    arr = ds["temperature"].values
    assert arr.shape == (1, 2, 2)

    paths = [request.path for request, _ in httpserver.log]
    assert "/collections/model/instances/f024" in paths
    assert any("/instances/f024/cube" in p for p in paths), f"paths: {paths}"
    assert not any(p == "/collections/model/cube" for p in paths), f"paths: {paths}"

    ds.close()


def test_open_with_drop_variables(httpserver: HTTPServer) -> None:
    """drop_variables removes variables from the dataset after build."""
    collection_url = _register_meta_and_probe(httpserver, "test_drop")

    ds = xr.open_dataset(collection_url, engine="edr", drop_variables=["temperature"])

    assert "temperature" not in ds.data_vars
    assert set(ds.coords) >= {"t", "y", "x"}

    ds.close()


def test_session_injection(httpserver: HTTPServer) -> None:
    """Injected httpx.Client with custom headers is used for all requests."""
    meta = _make_meta(httpserver, "auth_coll")
    httpserver.expect_request(
        "/collections/auth_coll",
        method="GET",
        headers={"x-api-key": "secret"},
    ).respond_with_json(meta)
    httpserver.expect_request(
        "/collections/auth_coll/cube",
        method="GET",
        headers={"x-api-key": "secret"},
    ).respond_with_json(COV_3D)

    client = httpx.Client(headers={"X-Api-Key": "secret"})
    try:
        collection_url = httpserver.url_for("/collections/auth_coll")
        ds = xr.open_dataset(
            collection_url,
            engine="edr",
            session=client,
            parameter_names=["temperature"],
        )
        arr = ds["temperature"].values
        assert arr.shape == (1, 2, 2)
        ds.close()

        # Session ownership contract: externally-owned client survives Dataset close.
        assert not client.is_closed
    finally:
        client.close()


def test_static_bbox_kwarg_propagates(httpserver: HTTPServer) -> None:
    """bbox= kwarg at open time becomes a static filter on cube fetches."""
    collection_url = _register_meta_and_probe(httpserver, "bbox_coll")
    httpserver.expect_request("/collections/bbox_coll/cube", method="GET").respond_with_json(COV_3D)

    ds = xr.open_dataset(
        collection_url,
        engine="edr",
        parameter_names=["temperature"],
        bbox=(10.0, 40.0, 10.5, 40.5),
    )
    arr = ds["temperature"].values
    assert arr.shape == (1, 2, 2)

    cube_requests = [request for request, _ in httpserver.log if "/cube" in request.path]
    assert len(cube_requests) >= 1
    data_fetch_qs = cube_requests[-1].query_string.decode()
    assert "bbox=" in data_fetch_qs
    assert "10.5" in data_fetch_qs
    assert "40.5" in data_fetch_qs

    ds.close()
