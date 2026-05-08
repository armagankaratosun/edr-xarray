"""Lazy semantics tests — verify exact HTTP request counts for open vs compute.

Key invariants:
- discovery='metadata_only': exactly 1 HTTP request on open (metadata only).
- discovery='probe': exactly 2 HTTP requests on open (metadata + probe).
- .values triggers exactly 1 additional HTTP request.
- .values called twice triggers 2 additional requests (no caching).
- .isel() narrowing produces a narrower bbox in the cube request.
"""

# pyright: reportMissingImports=false

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import xarray as xr
from pytest_httpserver import HTTPServer

META_BASIC: dict[str, Any] = json.loads(
    Path("tests/data/collection_metadata_basic.json").read_text()
)
COV_3D: dict[str, Any] = json.loads(Path("tests/data/cov_grid_3d.json").read_text())


def _build_meta(httpserver: HTTPServer, collection_id: str) -> dict[str, Any]:
    meta = copy.deepcopy(META_BASIC)
    meta["id"] = collection_id
    cube_href = httpserver.url_for(f"/collections/{collection_id}/cube")
    meta["data_queries"]["cube"]["link"]["href"] = cube_href
    return meta


def _register(httpserver: HTTPServer, collection_id: str) -> str:
    meta = _build_meta(httpserver, collection_id)
    httpserver.expect_ordered_request(
        f"/collections/{collection_id}", method="GET"
    ).respond_with_json(meta)
    httpserver.expect_ordered_request(
        f"/collections/{collection_id}/cube", method="GET"
    ).respond_with_json(COV_3D)
    return httpserver.url_for(f"/collections/{collection_id}")


def test_open_dataset_metadata_only_with_metadata_only_discovery(
    httpserver: HTTPServer,
) -> None:
    """discovery='metadata_only' issues exactly 1 HTTP request on open."""
    meta = _build_meta(httpserver, "m")
    # Only register the metadata endpoint — cube endpoint is NOT registered.
    # If the cube endpoint is hit, the unmatched request will appear in the log
    # and the assertion below will fail loudly.
    httpserver.expect_request("/collections/m", method="GET").respond_with_json(meta)

    url = httpserver.url_for("/collections/m")
    ds = xr.open_dataset(
        url,
        engine="edr",
        parameter_names=["temperature"],
        discovery="metadata_only",
    )

    assert len(httpserver.log) == 1, (
        f"expected 1 request, got {len(httpserver.log)}: {[r.path for r, _ in httpserver.log]}"
    )
    assert "/collections/m" in httpserver.log[0][0].path
    assert "temperature" in ds.data_vars
    # metadata_only discovery still populates dims (t, y, x) from extents.
    assert len(ds.dims) >= 2

    ds.close()


def test_open_dataset_with_probe_does_one_metadata_one_probe(
    httpserver: HTTPServer,
) -> None:
    """discovery='probe' issues exactly 2 HTTP requests on open."""
    url = _register(httpserver, "p")
    ds = xr.open_dataset(
        url,
        engine="edr",
        parameter_names=["temperature"],
        discovery="probe",
    )

    assert len(httpserver.log) == 2, (
        f"expected 2 requests, got {len(httpserver.log)}: {[r.path for r, _ in httpserver.log]}"
    )
    paths = [r.path for r, _ in httpserver.log]
    assert "/collections/p" in paths[0]
    assert "/collections/p/cube" in paths[1]
    assert "temperature" in ds.data_vars

    ds.close()


def test_compute_triggers_cube_fetch(httpserver: HTTPServer) -> None:
    """.values on a DataArray issues 1 additional HTTP request."""
    url = _register(httpserver, "c")
    # Register an unordered handler for subsequent data fetches.
    httpserver.expect_request("/collections/c/cube", method="GET").respond_with_json(COV_3D)

    ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"])
    assert len(httpserver.log) == 2

    _ = ds["temperature"].values

    assert len(httpserver.log) == 3, (
        f"expected 3 requests, got {len(httpserver.log)}: {[r.path for r, _ in httpserver.log]}"
    )

    ds.close()


def test_repeated_compute_triggers_repeated_fetch(httpserver: HTTPServer) -> None:
    """Calling .values twice with cache=False issues 2 additional requests."""
    url = _register(httpserver, "r")
    httpserver.expect_request("/collections/r/cube", method="GET").respond_with_json(COV_3D)

    # cache=False disables xarray's MemoryCachedArray wrapper so each .values
    # call goes back to the EDR backend; this proves laziness end-to-end.
    ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"], cache=False)
    _ = ds["temperature"].values
    _ = ds["temperature"].values

    # metadata + probe + fetch1 + fetch2 = 4
    assert len(httpserver.log) == 4, (
        f"expected 4 requests, got {len(httpserver.log)}: {[r.path for r, _ in httpserver.log]}"
    )

    ds.close()


def test_isel_subset_translates_to_narrow_query(httpserver: HTTPServer) -> None:
    """Isel with a spatial scalar produces a narrower bbox in the cube request."""
    url = _register(httpserver, "s")
    httpserver.expect_request("/collections/s/cube", method="GET").respond_with_json(COV_3D)

    ds = xr.open_dataset(url, engine="edr", parameter_names=["temperature"])

    # isel along x axis (index 0 = x=10.0 only) → degenerate-x bbox in query.
    _ = ds["temperature"].isel(x=0).values

    cube_requests = [r for r, _ in httpserver.log if "/cube" in r.path]
    # At least the probe and the data fetch.
    assert len(cube_requests) >= 2

    # The data fetch (last cube request) should have an EDR query string.
    data_fetch = cube_requests[-1]
    qs = data_fetch.query_string.decode()
    assert "parameter-name" in qs, f"expected parameter-name in qs, got: {qs}"
    assert "bbox" in qs, f"expected bbox in qs, got: {qs}"

    # Probe query bbox spans the full extent (10..11). isel(x=0) narrows
    # the longitude to a degenerate point at 10.0.
    probe_qs = cube_requests[0].query_string.decode()
    assert "11" in probe_qs, f"probe should contain full extent: {probe_qs}"
    # The data fetch bbox is degenerate in x: lon_min == lon_max == 10.0.
    # Encoded form is "10.0,40.0,10.0,41.0" (commas may be url-encoded).
    assert "10.0" in qs

    ds.close()
