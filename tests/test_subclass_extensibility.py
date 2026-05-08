"""Subclass extensibility tests for EdrDataStore.

These tests verify the documented hook contract:
each hook can be overridden and the override IS invoked.
"""

# pyright: reportMissingImports=false

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from pytest_httpserver import HTTPServer

from edr_xarray.coveragejson import CoverageData
from edr_xarray.errors import EdrUnsupportedFeatureError
from edr_xarray.indexer import AxisInfo
from edr_xarray.metadata import CollectionMetadata
from edr_xarray.store import EdrDataStore

META: dict[str, Any] = json.loads(Path("tests/data/collection_metadata_basic.json").read_text())
COV_3D: dict[str, Any] = json.loads(Path("tests/data/cov_grid_3d.json").read_text())


def _setup(httpserver: HTTPServer, collection_id: str = "hook_test") -> tuple[dict[str, Any], str]:
    """Register endpoints and return (meta, collection_url)."""
    meta = copy.deepcopy(META)
    meta["id"] = collection_id
    cube_href = httpserver.url_for(f"/collections/{collection_id}/cube")
    meta["data_queries"]["cube"]["link"]["href"] = cube_href
    httpserver.expect_ordered_request(f"/collections/{collection_id}").respond_with_json(meta)
    httpserver.expect_ordered_request(f"/collections/{collection_id}/cube").respond_with_json(
        COV_3D
    )
    httpserver.expect_request(f"/collections/{collection_id}/cube").respond_with_json(COV_3D)
    return meta, httpserver.url_for(f"/collections/{collection_id}")


def test_subclass_can_override_request_for_custom_auth(httpserver: HTTPServer) -> None:
    """_request override injects custom auth header on ALL requests."""

    class AuthStore(EdrDataStore):
        def _request(
            self,
            method: str,
            url: str,
            *,
            params: Mapping[str, str] | None = None,
            headers: Mapping[str, str] | None = None,
        ) -> httpx.Response:
            merged = dict(headers or {})
            merged["X-Api-Key"] = "secret"
            return super()._request(method, url, params=params, headers=merged)

    meta = copy.deepcopy(META)
    meta["id"] = "auth"
    cube_href = httpserver.url_for("/collections/auth/cube")
    meta["data_queries"]["cube"]["link"]["href"] = cube_href
    httpserver.expect_request(
        "/collections/auth", headers={"x-api-key": "secret"}
    ).respond_with_json(meta)
    httpserver.expect_request(
        "/collections/auth/cube", headers={"x-api-key": "secret"}
    ).respond_with_json(COV_3D)

    store = AuthStore(
        collection_url=httpserver.url_for("/collections/auth"),
        discovery="probe",
    )
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert len(httpserver.log) >= 3


def test_subclass_can_override_parse_metadata_for_extensions(httpserver: HTTPServer) -> None:
    """_parse_collection_metadata override can extract custom fields."""

    class ExtendedStore(EdrDataStore):
        extra_title: str | None = None

        def _parse_collection_metadata(self, payload: dict[str, Any]) -> CollectionMetadata:
            result = super()._parse_collection_metadata(payload)
            self.extra_title = payload.get("title", "(none)")
            return result

    _, url = _setup(httpserver, "ext")
    store = ExtendedStore(collection_url=url)
    store.build_dataset()

    assert store.extra_title == "Test Collection"


def test_subclass_can_override_build_cube_url_for_nonstandard_routing(
    httpserver: HTTPServer,
) -> None:
    """_build_cube_url override changes where cube requests go."""
    custom_cube_path = "/v2/alternate/cube"

    class CustomCubeStore(EdrDataStore):
        def _build_cube_url(self, collection_url: str, instance: str | None) -> str:
            return httpserver.url_for(custom_cube_path)

    meta = copy.deepcopy(META)
    meta["id"] = "custom"
    meta["data_queries"]["cube"]["link"]["href"] = httpserver.url_for("/collections/custom/cube")
    httpserver.expect_ordered_request("/collections/custom").respond_with_json(meta)
    # First-match (ordered) handler serves the probe; broad handler serves later data fetches.
    httpserver.expect_ordered_request(custom_cube_path).respond_with_json(COV_3D)
    httpserver.expect_request(custom_cube_path).respond_with_json(COV_3D)

    store = CustomCubeStore(
        collection_url=httpserver.url_for("/collections/custom"),
        discovery="probe",
    )
    ds = store.build_dataset()
    _ = ds["temperature"].values

    paths = [r.path for r, _ in httpserver.log]
    assert any(custom_cube_path in p for p in paths), f"custom path not found in {paths}"


def test_subclass_can_override_translate_indexer_to_inject_static_filters(
    httpserver: HTTPServer,
) -> None:
    """_translate_indexer override adds extra query params to cube requests."""

    class FilterStore(EdrDataStore):
        def _translate_indexer(
            self, key: tuple[Any, ...], axes: tuple[AxisInfo, ...]
        ) -> dict[str, str]:
            result = super()._translate_indexer(key, axes)
            result["min-value"] = "0.0"
            return result

    _, url = _setup(httpserver, "filter")
    store = FilterStore(collection_url=url)
    ds = store.build_dataset()
    _ = ds["temperature"].values

    cube_reqs = [r for r, _ in httpserver.log if "/cube" in r.path]
    assert len(cube_reqs) >= 2
    last_cube = cube_reqs[-1]
    qs = last_cube.query_string.decode()
    assert "min-value=0.0" in qs, f"min-value not found in {qs}"


def test_subclass_can_override_parse_coveragejson_for_extensions(
    httpserver: HTTPServer,
) -> None:
    """_parse_coveragejson override intercepts all CoverageJSON parsing."""
    call_count = [0]

    class InstrumentedStore(EdrDataStore):
        def _parse_coveragejson(self, payload: dict[str, Any]) -> CoverageData:
            call_count[0] += 1
            return super()._parse_coveragejson(payload)

    _, url = _setup(httpserver, "instrument")
    store = InstrumentedStore(collection_url=url)
    ds = store.build_dataset()
    _ = ds["temperature"].values

    assert call_count[0] >= 1


def test_all_7_hooks_have_default_implementations() -> None:
    """All 7 documented hooks are callable on EdrDataStore."""
    hook_names = [
        "_request",
        "_parse_collection_metadata",
        "_negotiate_output_format",
        "_build_cube_url",
        "_parse_coveragejson",
        "_translate_indexer",
        "_discover_axes",
    ]
    for hook_name in hook_names:
        assert hasattr(EdrDataStore, hook_name), f"missing hook: {hook_name}"
        assert callable(getattr(EdrDataStore, hook_name)), f"not callable: {hook_name}"


def test_subclass_with_extra_query_param_works_end_to_end(httpserver: HTTPServer) -> None:
    """Subclass that injects an extra query parameter works end-to-end."""

    class ExtraParamStore(EdrDataStore):
        """EdrDataStore subclass that appends a custom query parameter."""

        def _build_cube_url(self, collection_url: str, instance: str | None) -> str:
            return super()._build_cube_url(collection_url, instance)

        def _translate_indexer(
            self, key: tuple[Any, ...], axes: tuple[AxisInfo, ...]
        ) -> dict[str, str]:
            result = super()._translate_indexer(key, axes)
            result["custom"] = "value"
            return result

    _, url = _setup(httpserver, "extra_param")
    store = ExtraParamStore(collection_url=url)
    ds = store.build_dataset()
    _ = ds["temperature"].values

    cube_reqs = [r for r, _ in httpserver.log if "/cube" in r.path]
    last_cube_qs = cube_reqs[-1].query_string.decode()
    assert "custom=value" in last_cube_qs, f"custom param not found in {last_cube_qs}"


def test_negotiate_output_format_hook_can_raise_custom_error(
    httpserver: HTTPServer,
) -> None:
    """_negotiate_output_format override can raise EdrUnsupportedFeatureError."""

    class StrictFormatStore(EdrDataStore):
        def _negotiate_output_format(self, advertised: tuple[str, ...]) -> str:
            if "CoverageJSON" not in advertised:
                raise EdrUnsupportedFeatureError("StrictFormatStore requires CoverageJSON")
            return "CoverageJSON"

    _, url = _setup(httpserver, "strict_format")
    store = StrictFormatStore(collection_url=url)
    ds = store.build_dataset()
    assert "temperature" in ds.data_vars
