"""Tests for edr_xarray.store — EdrDataStore orchestration."""

# ruff: noqa: D103

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from typing import Any

import httpx
import pytest
from pytest_httpserver import HTTPServer

from edr_xarray.discovery import DiscoveryMode
from edr_xarray.errors import EdrMetadataError, EdrUnsupportedFeatureError
from edr_xarray.store import EdrDataStore

META_PAYLOAD = json.loads(Path("tests/data/collection_metadata_basic.json").read_text())
COV_3D = json.loads(Path("tests/data/cov_grid_3d.json").read_text())


def _meta(httpserver: HTTPServer, cube_path: str = "/collections/test/cube") -> dict[str, Any]:
    meta = copy.deepcopy(META_PAYLOAD)
    meta["id"] = "test"
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for(cube_path)
    return meta


def _requests(httpserver: HTTPServer) -> list[str]:
    assert httpserver.log is not None
    return [request.path for request, _ in httpserver.log]


def _store(
    httpserver: HTTPServer,
    *,
    discovery: DiscoveryMode = "probe",
    parameter_names: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    datetime: str | None = None,
    crs: str | None = None,
    z: float | str | None = None,
) -> EdrDataStore:
    return EdrDataStore(
        collection_url=httpserver.url_for("/collections/test"),
        discovery=discovery,
        parameter_names=parameter_names,
        bbox=bbox,
        datetime=datetime,
        crs=crs,
        z=z,
    )


def test_probe_mode_two_requests(httpserver: HTTPServer) -> None:
    meta = _meta(httpserver)
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(meta)
    httpserver.expect_ordered_request("/collections/test/cube", method="GET").respond_with_json(
        COV_3D
    )

    store = _store(httpserver, discovery="probe")
    ds = store.build_dataset()

    requests = _requests(httpserver)
    assert len(requests) == 2
    assert requests == ["/collections/test", "/collections/test/cube"]
    assert "temperature" in ds.data_vars
    store.close()


def test_metadata_only_one_request(httpserver: HTTPServer) -> None:
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )

    store = _store(httpserver, discovery="metadata_only")
    ds = store.build_dataset()

    assert _requests(httpserver) == ["/collections/test"]
    assert ds["temperature"].shape == (1, 2, 2)
    store.close()


def test_invalid_discovery_mode_raises() -> None:
    with pytest.raises(ValueError, match="invalid discovery mode"):
        EdrDataStore(collection_url="http://test/collections/test", discovery="surprise")


def test_build_dataset_returns_expected_data_vars(httpserver: HTTPServer) -> None:
    meta = _meta(httpserver)
    meta["parameter_names"]["humidity"] = copy.deepcopy(meta["parameter_names"]["temperature"])
    httpserver.expect_request("/collections/test", method="GET").respond_with_json(meta)

    store = _store(httpserver, discovery="metadata_only")
    ds = store.build_dataset()

    assert set(ds.data_vars) == {"temperature", "humidity"}
    store.close()


def test_build_dataset_returns_correct_dims(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )

    store = _store(httpserver, discovery="metadata_only")
    ds = store.build_dataset()

    assert ds["temperature"].dims == ("t", "y", "x")
    assert dict(ds.sizes) == {"t": 1, "y": 2, "x": 2}
    store.close()


def test_parameter_names_filter(httpserver: HTTPServer) -> None:
    meta = _meta(httpserver)
    meta["parameter_names"]["humidity"] = copy.deepcopy(meta["parameter_names"]["temperature"])
    httpserver.expect_request("/collections/test", method="GET").respond_with_json(meta)

    store = _store(httpserver, discovery="metadata_only", parameter_names=["temperature"])
    ds = store.build_dataset()

    assert set(ds.data_vars) == {"temperature"}
    assert set(ds.coords) == {"t", "y", "x"}
    store.close()


def test_parameter_names_unknown_raises(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )

    store = _store(httpserver, discovery="metadata_only", parameter_names=["wind"])
    with pytest.raises(EdrMetadataError, match="not found"):
        store.build_dataset()
    store.close()


def test_no_coveragejson_advertised_raises(httpserver: HTTPServer) -> None:
    meta = _meta(httpserver)
    meta["data_queries"]["cube"]["link"]["variables"]["output_formats"] = ["GeoJSON"]
    httpserver.expect_request("/collections/test", method="GET").respond_with_json(meta)

    store = _store(httpserver, discovery="metadata_only")
    with pytest.raises(EdrUnsupportedFeatureError, match="CoverageJSON"):
        store.build_dataset()
    store.close()


def test_close_closes_owned_transport() -> None:
    store = EdrDataStore(collection_url="https://example.test/collections/test")

    store.close()

    assert store._transport._session.is_closed


def test_injected_session_not_closed() -> None:
    session = httpx.Client()
    try:
        store = EdrDataStore(
            collection_url="https://example.test/collections/test",
            session=session,
        )
        store.close()
        assert not session.is_closed
    finally:
        session.close()


def test_bbox_kwarg_propagates_to_extra_params(httpserver: HTTPServer) -> None:
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "bbox": "10,40,11,41",
            "datetime": "2025-01-01T00:00:00Z",
            "f": "CoverageJSON",
            "parameter-name": "temperature",
        },
    ).respond_with_json(COV_3D)

    store = _store(httpserver, discovery="metadata_only", bbox=(10, 40, 11, 41))
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert _requests(httpserver) == ["/collections/test", "/collections/test/cube"]
    store.close()


def test_datetime_kwarg_propagates(httpserver: HTTPServer) -> None:
    dt = "2025-01-01T00:00:00Z"
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "datetime": dt,
            "bbox": "10.0,40.0,11.0,41.0",
            "f": "CoverageJSON",
            "parameter-name": "temperature",
        },
    ).respond_with_json(COV_3D)

    store = _store(httpserver, discovery="metadata_only", datetime=dt)
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert len(_requests(httpserver)) == 2
    store.close()


def test_crs_not_in_allowed_raises(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )

    store = _store(httpserver, discovery="metadata_only", crs="EPSG:3857")
    with pytest.raises(EdrUnsupportedFeatureError, match="EPSG:3857"):
        store.build_dataset()
    store.close()


def test_subclass_overrides_build_cube_url(httpserver: HTTPServer) -> None:
    class CustomStore(EdrDataStore):
        def _build_cube_url(self, collection_url: str, instance: str | None) -> str:
            return httpserver.url_for("/custom/cube")

    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request("/custom/cube", method="GET").respond_with_json(COV_3D)

    store = CustomStore(collection_url=httpserver.url_for("/collections/test"), discovery="probe")
    ds = store.build_dataset()

    assert "temperature" in ds
    assert _requests(httpserver)[-1] == "/custom/cube"
    store.close()


def test_all_7_hooks_in_dir() -> None:
    hooks = {
        "_request",
        "_parse_collection_metadata",
        "_negotiate_output_format",
        "_build_cube_url",
        "_parse_coveragejson",
        "_translate_indexer",
        "_discover_axes",
    }

    assert hooks <= set(dir(EdrDataStore))


def test_build_dataset_is_lazy(httpserver: HTTPServer) -> None:
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request("/collections/test/cube", method="GET").respond_with_json(
        COV_3D
    )

    store = _store(httpserver, discovery="probe")
    ds = store.build_dataset()

    assert len(_requests(httpserver)) == 2
    assert ds["temperature"].shape == (1, 2, 2)
    assert len(_requests(httpserver)) == 2
    store.close()


def test_z_and_crs_kwargs_propagate_to_extra_params(httpserver: HTTPServer) -> None:
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "crs": "CRS84",
            "z": "1000.0",
            "datetime": "2025-01-01T00:00:00Z",
            "bbox": "10.0,40.0,11.0,41.0",
            "f": "CoverageJSON",
            "parameter-name": "temperature",
        },
    ).respond_with_json(COV_3D)

    store = _store(httpserver, discovery="metadata_only", crs="CRS84", z=1000.0)
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert len(_requests(httpserver)) == 2
    store.close()


def test_invalid_metadata_json_raises_metadata_error(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/collections/test", method="GET").respond_with_data("not-json")

    store = _store(httpserver, discovery="metadata_only")
    with pytest.raises(EdrMetadataError, match="valid JSON"):
        store.build_dataset()
    store.close()


def test_store_pickle_roundtrip_restores_transport() -> None:
    store = EdrDataStore(
        collection_url="https://example.test/collections/test",
        timeout=3.0,
    )
    blob = pickle.dumps(store)
    restored = pickle.loads(blob)

    assert restored.collection_url == store.collection_url
    assert restored._transport is not store._transport
    restored.close()
    store.close()
