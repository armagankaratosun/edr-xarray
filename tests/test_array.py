"""Tests for edr_xarray.array — lazy BackendArray fetches via store hooks."""

# pyright: reportMissingImports=false
# ruff: noqa: D103, ANN401

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import numpy as np
import pytest
from xarray.backends import BackendArray
from xarray.core import indexing

from edr_xarray.array import EdrBackendArray
from edr_xarray.coveragejson import CoverageData, parse_coverage
from edr_xarray.errors import EdrCoverageJsonError, EdrServerError
from edr_xarray.indexer import AxisInfo

_DATA_DIR = Path(__file__).parent / "data"


def load_cov_grid_3d() -> dict[str, Any]:
    return json.loads((_DATA_DIR / "cov_grid_3d.json").read_text())


def make_mock_store(cov_payload: dict[str, Any]) -> MagicMock:
    """Create a mock store whose hooks serve a given CoverageJSON payload."""
    store = MagicMock()
    store._translate_indexer.return_value = {}
    store._request.return_value = httpx.Response(200, json=cov_payload)
    store._parse_coveragejson.side_effect = lambda p: parse_coverage(p)
    return store


class PickleableStore:
    """Small pickle-friendly store double for array pickle tests."""

    def __init__(self, cov_payload: dict[str, Any]) -> None:
        """Store the CoverageJSON payload served by this double."""
        self.cov_payload = cov_payload

    def _translate_indexer(
        self, key: tuple[int | slice, ...], axes: tuple[AxisInfo, ...]
    ) -> dict[str, str]:
        return {}

    def _request(self, method: str, url: str, *, params: dict[str, str]) -> httpx.Response:
        return httpx.Response(200, json=self.cov_payload)

    def _parse_coveragejson(self, payload: dict[str, Any]) -> CoverageData:
        return parse_coverage(payload)


def make_3d_axes() -> tuple[AxisInfo, ...]:
    return (
        AxisInfo(
            name="t",
            values=np.array(["2025-01-01T00:00:00"], dtype="datetime64[ns]"),
            kind="t",
        ),
        AxisInfo(name="y", values=np.array([40.0, 41.0]), kind="y"),
        AxisInfo(name="x", values=np.array([10.0, 11.0]), kind="x"),
    )


def make_array(
    store: Any,
    axes: tuple[AxisInfo, ...] | None = None,
    param_id: str = "temperature",
    extra_query_params: dict[str, str] | None = None,
) -> EdrBackendArray:
    if axes is None:
        axes = make_3d_axes()
    shape = tuple(len(a.values) for a in axes)
    return EdrBackendArray(
        store=store,
        cube_url="http://test/collections/c/cube",
        parameter_id=param_id,
        axes=axes,
        shape=shape,
        dtype=np.dtype("float64"),
        extra_query_params=extra_query_params,
    )


def test_construction_does_not_trigger_http() -> None:
    store = make_mock_store(load_cov_grid_3d())
    make_array(store)
    assert store._request.call_count == 0


def test_shape_and_dtype_accessible() -> None:
    arr = make_array(make_mock_store(load_cov_grid_3d()))
    assert arr.shape == (1, 2, 2)
    assert arr.dtype == np.dtype("float64")


def test_is_backend_array() -> None:
    assert isinstance(make_array(make_mock_store(load_cov_grid_3d())), BackendArray)


def test_getitem_triggers_http_request() -> None:
    store = make_mock_store(load_cov_grid_3d())
    arr = make_array(store)
    arr[indexing.BasicIndexer((slice(None),) * 3)]
    assert store._request.call_count == 1


def test_getitem_routes_through_all_three_hooks() -> None:
    store = make_mock_store(load_cov_grid_3d())
    arr = make_array(store)
    arr[indexing.BasicIndexer((slice(None),) * 3)]
    store._translate_indexer.assert_called_once()
    store._request.assert_called_once()
    store._parse_coveragejson.assert_called_once()


def test_getitem_includes_parameter_name_in_query() -> None:
    store = make_mock_store(load_cov_grid_3d())
    make_array(store)[indexing.BasicIndexer((slice(None),) * 3)]
    assert store._request.call_args.kwargs["params"]["parameter-name"] == "temperature"


def test_getitem_includes_f_coveragejson_in_query() -> None:
    store = make_mock_store(load_cov_grid_3d())
    make_array(store)[indexing.BasicIndexer((slice(None),) * 3)]
    assert store._request.call_args.kwargs["params"]["f"] == "CoverageJSON"


def test_extra_query_params_merged() -> None:
    store = make_mock_store(load_cov_grid_3d())
    arr = make_array(store, extra_query_params={"crs": "CRS84"})
    arr[indexing.BasicIndexer((slice(None),) * 3)]
    assert store._request.call_args.kwargs["params"]["crs"] == "CRS84"


def test_extra_params_win_over_defaults() -> None:
    store = make_mock_store(load_cov_grid_3d())
    arr = make_array(store, extra_query_params={"f": "NetCDF"})
    arr[indexing.BasicIndexer((slice(None),) * 3)]
    assert store._request.call_args.kwargs["params"]["f"] == "NetCDF"


def test_axis_transposition_corrects_order() -> None:
    payload = copy.deepcopy(load_cov_grid_3d())
    payload["ranges"]["temperature"]["axisNames"] = ["x", "y", "t"]
    payload["ranges"]["temperature"]["shape"] = [2, 2, 1]
    payload["ranges"]["temperature"]["values"] = [1.0, 2.0, 3.0, 4.0]
    store = make_mock_store(payload)

    result = make_array(store)[indexing.BasicIndexer((slice(None),) * 3)]

    expected = np.array([[[1.0, 3.0], [2.0, 4.0]]])
    assert result.shape == (1, 2, 2)
    assert np.array_equal(result, expected)


def test_missing_parameter_range_raises() -> None:
    payload = copy.deepcopy(load_cov_grid_3d())
    payload["parameters"]["humidity"] = payload["parameters"].pop("temperature")
    payload["ranges"]["humidity"] = payload["ranges"].pop("temperature")
    store = make_mock_store(payload)

    with pytest.raises(EdrCoverageJsonError, match="no range"):
        make_array(store)[indexing.BasicIndexer((slice(None),) * 3)]


def test_pickle_roundtrip() -> None:
    arr = make_array(PickleableStore(load_cov_grid_3d()))
    blob = pickle.dumps(arr)
    arr2 = pickle.loads(blob)
    assert arr2.shape == arr.shape
    assert arr2._store is not None


def test_lazily_indexed_array_wrapping() -> None:
    arr = make_array(make_mock_store(load_cov_grid_3d()))
    lazy = indexing.LazilyIndexedArray(arr)
    assert lazy.shape == arr.shape


def test_getitem_returns_correct_values() -> None:
    store = make_mock_store(load_cov_grid_3d())
    result = make_array(store)[indexing.BasicIndexer((slice(None),) * 3)]
    expected = np.array([[[273.15, 274.15], [275.15, 276.15]]])
    assert result.shape == (1, 2, 2)
    assert np.allclose(result, expected)


def test_outer_indexer_decomposed_by_adapter() -> None:
    store = make_mock_store(load_cov_grid_3d())
    result = make_array(store)[indexing.OuterIndexer((np.array([0]),) * 3)]
    assert result.shape == (1, 1, 1)
    assert np.allclose(result, np.array([[[273.15]]]))


def test_request_errors_propagate() -> None:
    store = make_mock_store(load_cov_grid_3d())
    store._request.side_effect = EdrServerError("boom", status_code=500)
    with pytest.raises(EdrServerError, match="boom"):
        make_array(store)[indexing.BasicIndexer((slice(None),) * 3)]
