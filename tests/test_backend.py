"""Tests for edr_xarray.backend xarray backend entrypoint."""

# ruff: noqa: D103

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import xarray as xr
from pytest_httpserver import HTTPServer
from xarray.backends import list_engines

from edr_xarray.backend import EdrBackendEntrypoint

META: dict[str, Any] = json.loads(Path("tests/data/collection_metadata_basic.json").read_text())
COV_3D: dict[str, Any] = json.loads(Path("tests/data/cov_grid_3d.json").read_text())


def setup_server(httpserver: HTTPServer, collection_id: str = "test_collection") -> str:
    """Register metadata and probe endpoints, returning the collection URL."""
    meta = copy.deepcopy(META)
    cube_href = httpserver.url_for(f"/collections/{collection_id}/cube")
    meta["data_queries"]["cube"]["link"]["href"] = cube_href
    meta["id"] = collection_id
    httpserver.expect_ordered_request(
        f"/collections/{collection_id}", method="GET"
    ).respond_with_json(meta)
    httpserver.expect_ordered_request(
        f"/collections/{collection_id}/cube", method="GET"
    ).respond_with_json(COV_3D)
    return httpserver.url_for(f"/collections/{collection_id}")


def request_paths(httpserver: HTTPServer) -> list[str]:
    """Return paths requested from the test HTTP server."""
    assert httpserver.log is not None
    return [request.path for request, _ in httpserver.log]


def test_engine_registered() -> None:
    assert "edr" in list_engines()


def test_engine_is_edr_backend_entrypoint() -> None:
    assert isinstance(list_engines()["edr"], EdrBackendEntrypoint)


def test_open_dataset_returns_dataset(httpserver: HTTPServer) -> None:
    url = setup_server(httpserver)

    ds = xr.open_dataset(url, engine="edr")

    assert isinstance(ds, xr.Dataset)
    ds.close()


def test_open_dataset_has_expected_data_vars(httpserver: HTTPServer) -> None:
    url = setup_server(httpserver)

    ds = xr.open_dataset(url, engine="edr")

    assert "temperature" in ds.data_vars
    ds.close()


def test_guess_can_open_collection_url() -> None:
    assert EdrBackendEntrypoint().guess_can_open("http://srv/collections/foo")


def test_guess_can_open_items_url_false() -> None:
    assert not EdrBackendEntrypoint().guess_can_open("http://srv/collections/foo/items")


def test_guess_can_open_api_url_false() -> None:
    assert not EdrBackendEntrypoint().guess_can_open("http://srv/api")


def test_guess_can_open_non_string_false() -> None:
    assert not EdrBackendEntrypoint().guess_can_open(123)


def test_bad_url_raises_value_error() -> None:
    with pytest.raises(ValueError, match="/collections"):
        xr.open_dataset("http://example.com/api", engine="edr")


def test_drop_variables_removes_variable(httpserver: HTTPServer) -> None:
    meta = copy.deepcopy(META)
    meta["parameter_names"]["humidity"] = copy.deepcopy(meta["parameter_names"]["temperature"])
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for(
        "/collections/test_collection/cube"
    )
    httpserver.expect_ordered_request(
        "/collections/test_collection", method="GET"
    ).respond_with_json(meta)
    httpserver.expect_ordered_request(
        "/collections/test_collection/cube", method="GET"
    ).respond_with_json(COV_3D)

    ds = xr.open_dataset(
        httpserver.url_for("/collections/test_collection"),
        engine="edr",
        drop_variables=["temperature"],
    )

    assert "temperature" not in ds.data_vars
    assert "humidity" in ds.data_vars
    ds.close()


def test_open_dataset_is_lazy(httpserver: HTTPServer) -> None:
    url = setup_server(httpserver)

    ds = xr.open_dataset(url, engine="edr")

    assert request_paths(httpserver) == [
        "/collections/test_collection",
        "/collections/test_collection/cube",
    ]
    assert ds["temperature"].shape == (1, 2, 2)
    assert request_paths(httpserver) == [
        "/collections/test_collection",
        "/collections/test_collection/cube",
    ]
    ds.close()


def test_matching_server_url_can_be_opened_by_edr_backend(httpserver: HTTPServer) -> None:
    url = setup_server(httpserver)

    assert EdrBackendEntrypoint().guess_can_open(url)
    ds = xr.open_dataset(url, engine="edr")
    assert "temperature" in ds.data_vars
    ds.close()
