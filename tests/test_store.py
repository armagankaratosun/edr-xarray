"""Tests for edr_xarray.store — EdrDataStore orchestration."""

# ruff: noqa: D103

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from pytest_httpserver import HTTPServer

from edr_xarray.discovery import DiscoveryMode
from edr_xarray.errors import EdrMetadataError, EdrUnsupportedFeatureError
from edr_xarray.store import EdrDataStore

META_PAYLOAD = json.loads(Path("tests/data/collection_metadata_basic.json").read_text())
COV_3D = json.loads(Path("tests/data/cov_grid_3d.json").read_text())
COV_4D = json.loads(Path("tests/data/cov_grid_4d.json").read_text())


def _meta(httpserver: HTTPServer, cube_path: str = "/collections/test/cube") -> dict[str, Any]:
    meta = copy.deepcopy(META_PAYLOAD)
    meta["id"] = "test"
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for(cube_path)
    return meta


def _meta_with_instances(httpserver: HTTPServer) -> dict[str, Any]:
    meta = _meta(httpserver)
    meta["data_queries"]["instances"] = {
        "link": {"href": httpserver.url_for("/collections/test/instances")}
    }
    return meta


def _instance_meta(
    httpserver: HTTPServer,
    *,
    instance: str = "f024",
    parameter_name: str = "temperature",
) -> dict[str, Any]:
    meta = copy.deepcopy(META_PAYLOAD)
    meta["id"] = instance
    meta["title"] = f"Instance {instance}"
    meta["description"] = f"Metadata for instance {instance}"
    meta["extent"]["spatial"]["bbox"] = [[20.0, 50.0, 21.0, 51.0]]
    meta["extent"]["temporal"]["interval"] = [["2025-02-01T00:00:00Z", "2025-02-02T00:00:00Z"]]
    meta["extent"]["temporal"]["values"] = [
        "2025-02-01T00:00:00Z",
        "2025-02-02T00:00:00Z",
    ]
    if parameter_name != "temperature":
        parameter = copy.deepcopy(META_PAYLOAD["parameter_names"]["temperature"])
        parameter["observedProperty"]["id"] = parameter_name
        parameter["observedProperty"]["label"]["en"] = parameter_name
        meta["parameter_names"] = {parameter_name: parameter}
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for(
        f"/collections/test/instances/{instance}/cube"
    )
    return meta


def _cov_with_two_times(parameter_name: str = "temperature") -> dict[str, Any]:
    cov = copy.deepcopy(COV_3D)
    cov["domain"]["axes"]["x"]["values"] = [20.0, 21.0]
    cov["domain"]["axes"]["y"]["values"] = [50.0, 51.0]
    cov["domain"]["axes"]["t"]["values"] = [
        "2025-02-01T00:00:00Z",
        "2025-02-02T00:00:00Z",
    ]
    if parameter_name != "temperature":
        cov["parameters"][parameter_name] = cov["parameters"].pop("temperature")
        cov["ranges"][parameter_name] = cov["ranges"].pop("temperature")
    cov["ranges"][parameter_name]["axisNames"] = ["t", "y", "x"]
    cov["ranges"][parameter_name]["shape"] = [2, 2, 2]
    cov["ranges"][parameter_name]["values"] = [
        273.15,
        274.15,
        275.15,
        276.15,
        277.15,
        278.15,
        279.15,
        280.15,
    ]
    return cov


def _requests(httpserver: HTTPServer) -> list[str]:
    assert httpserver.log is not None
    return [request.path for request, _ in httpserver.log]


def _store(
    httpserver: HTTPServer,
    *,
    discovery: DiscoveryMode = "probe",
    parameter_names: list[str] | None = None,
    instance: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    datetime: str | None = None,
    crs: str | None = None,
    z: float | str | None = None,
) -> EdrDataStore:
    return EdrDataStore(
        collection_url=httpserver.url_for("/collections/test"),
        instance=instance,
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


def test_probe_mode_uses_open_datetime_for_axis_discovery(httpserver: HTTPServer) -> None:
    datetime = "2025-01-01T00:00:00Z/2025-01-03T00:00:00Z"
    cov = copy.deepcopy(COV_3D)
    cov["domain"]["axes"]["t"]["values"] = [
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
        "2025-01-03T00:00:00Z",
    ]
    cov["ranges"]["temperature"]["shape"] = [3, 2, 2]
    cov["ranges"]["temperature"]["values"] = [
        273.15,
        274.15,
        275.15,
        276.15,
        277.15,
        278.15,
        279.15,
        280.15,
        281.15,
        282.15,
        283.15,
        284.15,
    ]
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "bbox": "10.0,40.0,11.0,41.0",
            "datetime": datetime,
            "parameter-name": "temperature",
            "f": "CoverageJSON",
        },
    ).respond_with_json(cov)

    store = _store(httpserver, discovery="probe", datetime=datetime)
    ds = store.build_dataset()

    assert ds.sizes["t"] == 3
    assert str(ds.coords["t"].values[1]) == "2025-01-02T00:00:00.000000000"
    store.close()


def test_probe_mode_uses_open_z_for_axis_discovery(httpserver: HTTPServer) -> None:
    cov = copy.deepcopy(COV_4D)
    cov["domain"]["axes"]["z"]["values"] = [850.0]
    cov["ranges"]["temperature"]["shape"] = [1, 1, 2, 2]
    cov["ranges"]["temperature"]["values"] = [273.15, 274.15, 275.15, 276.15]
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "bbox": "10.0,40.0,11.0,41.0",
            "datetime": "2025-01-01T00:00:00Z",
            "z": "850.0",
            "parameter-name": "temperature",
            "f": "CoverageJSON",
        },
    ).respond_with_json(cov)

    store = _store(httpserver, discovery="probe", z=850.0)
    ds = store.build_dataset()

    assert ds.sizes["z"] == 1
    assert ds.coords["z"].values.tolist() == [850.0]
    store.close()


def test_probe_mode_uses_selected_parameter_for_axis_discovery(
    httpserver: HTTPServer,
) -> None:
    meta = _meta(httpserver)
    meta["parameter_names"]["humidity"] = copy.deepcopy(meta["parameter_names"]["temperature"])
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(meta)
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "bbox": "10.0,40.0,11.0,41.0",
            "datetime": "2025-01-01T00:00:00Z",
            "parameter-name": "humidity",
            "f": "CoverageJSON",
        },
    ).respond_with_json(COV_3D)

    store = _store(httpserver, discovery="probe", parameter_names=["humidity"])
    ds = store.build_dataset()

    assert set(ds.data_vars) == {"humidity"}
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


def test_sel_on_dimension_coordinates_stays_lazy(httpserver: HTTPServer) -> None:
    meta = _meta(httpserver)
    meta["extent"]["vertical"] = {
        "interval": [[500.0, 1000.0]],
        "values": [1000.0, 850.0, 500.0],
        "vrs": "EPSG:5714",
    }
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(meta)

    store = _store(httpserver, discovery="metadata_only")
    ds = store.build_dataset()
    selected = ds.sel(
        t=np.datetime64("2025-01-01T00:00:00"),
        z=850.0,
        y=40.0,
        x=10.0,
    )

    assert selected["temperature"].shape == ()
    assert _requests(httpserver) == ["/collections/test"]
    store.close()


def test_instance_metadata_only_uses_instance_metadata(httpserver: HTTPServer) -> None:
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta_with_instances(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/instances/f024", method="GET"
    ).respond_with_json(_instance_meta(httpserver, parameter_name="humidity"))

    store = _store(
        httpserver,
        discovery="metadata_only",
        instance="f024",
        parameter_names=["humidity"],
    )
    ds = store.build_dataset()

    assert _requests(httpserver) == ["/collections/test", "/collections/test/instances/f024"]
    assert set(ds.data_vars) == {"humidity"}
    assert ds.attrs["title"] == "Instance f024"
    assert ds.sizes["t"] == 2
    assert ds.coords["x"].values.tolist() == [20.0, 21.0]
    store.close()


def test_instance_metadata_drives_fallback_cube_query_params(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta_with_instances(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/instances/f024", method="GET"
    ).respond_with_json(_instance_meta(httpserver))
    httpserver.expect_ordered_request(
        "/collections/test/instances/f024/cube",
        method="GET",
        query_string={
            "bbox": "20.0,50.0,21.0,51.0",
            "datetime": "2025-02-01T00:00:00Z/2025-02-02T00:00:00Z",
            "f": "CoverageJSON",
            "parameter-name": "temperature",
        },
    ).respond_with_json(_cov_with_two_times())

    store = _store(httpserver, discovery="metadata_only", instance="f024")
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert _requests(httpserver) == [
        "/collections/test",
        "/collections/test/instances/f024",
        "/collections/test/instances/f024/cube",
    ]
    store.close()


def test_instance_probe_fetches_instance_metadata_before_cube_probe(
    httpserver: HTTPServer,
) -> None:
    probe_cov = copy.deepcopy(COV_3D)
    probe_cov["domain"]["axes"]["x"]["values"] = [20.0, 21.0]
    probe_cov["domain"]["axes"]["y"]["values"] = [50.0, 51.0]
    probe_cov["domain"]["axes"]["t"]["values"] = ["2025-02-01T00:00:00Z"]
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(
        _meta_with_instances(httpserver)
    )
    httpserver.expect_ordered_request(
        "/collections/test/instances/f024", method="GET"
    ).respond_with_json(_instance_meta(httpserver))
    httpserver.expect_ordered_request(
        "/collections/test/instances/f024/cube",
        method="GET",
        query_string={
            "bbox": "20.0,50.0,21.0,51.0",
            "datetime": "2025-02-01T00:00:00Z",
            "parameter-name": "temperature",
            "f": "CoverageJSON",
        },
    ).respond_with_json(probe_cov)

    store = _store(httpserver, discovery="probe", instance="f024")
    ds = store.build_dataset()

    assert _requests(httpserver) == [
        "/collections/test",
        "/collections/test/instances/f024",
        "/collections/test/instances/f024/cube",
    ]
    assert ds.sizes["t"] == 2
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


def test_parameter_names_empty_raises() -> None:
    with pytest.raises(ValueError, match="parameter_names"):
        EdrDataStore(
            collection_url="http://test/collections/test",
            discovery="metadata_only",
            parameter_names=[],
        )


def test_interval_only_metadata_defaults_probe_and_fetch_to_first_time(
    httpserver: HTTPServer,
) -> None:
    meta = _meta(httpserver)
    meta["extent"]["temporal"]["interval"] = [["2025-01-01T00:00:00Z", "2025-01-03T00:00:00Z"]]
    del meta["extent"]["temporal"]["values"]
    expected_query = {
        "bbox": "10.0,40.0,11.0,41.0",
        "datetime": "2025-01-01T00:00:00Z",
        "parameter-name": "temperature",
        "f": "CoverageJSON",
    }
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(meta)
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string=expected_query,
    ).respond_with_json(COV_3D)
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string=expected_query,
    ).respond_with_json(COV_3D)

    store = _store(httpserver, discovery="probe")
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert _requests(httpserver) == [
        "/collections/test",
        "/collections/test/cube",
        "/collections/test/cube",
    ]
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


def test_crs_validation_uses_cube_and_top_level_crs_union(httpserver: HTTPServer) -> None:
    meta = _meta(httpserver)
    top_level_crs = meta["crs"][0]
    cube_crs = meta["data_queries"]["cube"]["link"]["variables"]["crs_details"][0]["crs"]
    assert top_level_crs != cube_crs
    httpserver.expect_ordered_request("/collections/test", method="GET").respond_with_json(meta)
    httpserver.expect_ordered_request(
        "/collections/test/cube",
        method="GET",
        query_string={
            "crs": top_level_crs,
            "datetime": "2025-01-01T00:00:00Z",
            "bbox": "10.0,40.0,11.0,41.0",
            "f": "CoverageJSON",
            "parameter-name": "temperature",
        },
    ).respond_with_json(COV_3D)

    store = _store(httpserver, discovery="metadata_only", crs=top_level_crs)
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert len(_requests(httpserver)) == 2
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
