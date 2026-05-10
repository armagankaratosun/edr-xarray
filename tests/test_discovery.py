"""Tests for edr_xarray.discovery — coordinate axis discovery strategies."""

# ruff: noqa: D103

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import numpy as np
import pytest

from edr_xarray.coveragejson import parse_coverage
from edr_xarray.discovery import axis_kind, discover_axes
from edr_xarray.errors import (
    EdrCoverageJsonError,
    EdrMetadataError,
    EdrServerError,
    EdrUnsupportedFeatureError,
)
from edr_xarray.metadata import (
    CollectionMetadata,
    CubeLink,
    ParameterDefinition,
    SpatialExtent,
    TemporalExtent,
    VerticalExtent,
)

_DATA_DIR = Path(__file__).parent / "data"


def make_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        headers={"content-type": "application/json"},
        json=payload,
    )


def _load_payload(name: str) -> dict[str, Any]:
    return json.loads((_DATA_DIR / name).read_text())


def _make_metadata(
    *,
    with_temporal_values: bool = True,
    with_vertical: bool = False,
    with_vertical_values: bool = True,
    with_temporal: bool = True,
) -> CollectionMetadata:
    vertical = None
    if with_vertical:
        values = (1000.0, 850.0) if with_vertical_values else None
        vertical = VerticalExtent(interval=(500.0, 1000.0), values=values, vrs=None)
    temporal = None
    if with_temporal:
        temporal = TemporalExtent(
            interval=("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"),
            values=("2025-01-01T00:00:00Z",) if with_temporal_values else None,
        )
    return CollectionMetadata(
        id="test",
        title=None,
        description=None,
        spatial=SpatialExtent(bbox=(10.0, 40.0, 11.0, 41.0), crs=None),
        temporal=temporal,
        vertical=vertical,
        crs_options=("CRS84",),
        parameters={
            "temperature": ParameterDefinition(
                id="temperature",
                unit="K",
                standard_name="air_temperature",
                long_name="Air temperature",
                cell_methods=None,
            )
        },
        cube_link=CubeLink(
            href="http://test/collections/test/cube",
            output_formats=("CoverageJSON",),
            default_output_format="CoverageJSON",
            crs_options=("CRS84",),
        ),
        instances_link=None,
    )


def test_probe_mode_returns_axes_from_single_http_call(
    sample_cov_grid_3d: dict[str, Any],
) -> None:
    request_callable = MagicMock(return_value=make_response(sample_cov_grid_3d))

    axes = discover_axes(
        _make_metadata(),
        mode="probe",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
    )

    assert [(axis.name, axis.kind) for axis in axes] == [("t", "t"), ("y", "y"), ("x", "x")]
    assert axes[0].values.dtype == np.dtype("datetime64[ns]")
    assert request_callable.call_count == 1


def test_probe_mode_4d_includes_z_axis(sample_cov_grid_4d: dict[str, Any]) -> None:
    request_callable = MagicMock(return_value=make_response(sample_cov_grid_4d))

    axes = discover_axes(
        _make_metadata(),
        mode="probe",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
    )

    assert [(axis.name, axis.kind) for axis in axes] == [
        ("t", "t"),
        ("z", "z"),
        ("y", "y"),
        ("x", "x"),
    ]
    assert np.allclose(axes[1].values, [1000.0, 850.0, 500.0])


def test_probe_mode_uses_collection_bbox_and_first_param_in_request(
    sample_cov_grid_3d: dict[str, Any],
) -> None:
    request_callable = MagicMock(return_value=make_response(sample_cov_grid_3d))

    discover_axes(
        _make_metadata(),
        mode="probe",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance="ignored",
    )

    request_callable.assert_called_once()
    assert request_callable.call_args.args == ("GET", "http://test/cube")
    assert request_callable.call_args.kwargs["params"] == {
        "bbox": "10.0,40.0,11.0,41.0",
        "datetime": "2025-01-01T00:00:00Z",
        "parameter-name": "temperature",
        "f": "CoverageJSON",
    }


def test_probe_mode_uses_user_bbox_when_supplied(
    sample_cov_grid_3d: dict[str, Any],
) -> None:
    request_callable = MagicMock(return_value=make_response(sample_cov_grid_3d))

    discover_axes(
        _make_metadata(),
        mode="probe",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
        user_bbox=(10.2, 40.2, 10.4, 40.4),
    )

    assert request_callable.call_args.kwargs["params"]["bbox"] == "10.2,40.2,10.4,40.4"


def test_probe_mode_uses_user_datetime_when_supplied(
    sample_cov_grid_3d: dict[str, Any],
) -> None:
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["domain"]["axes"]["t"]["values"] = [
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
        "2025-01-03T00:00:00Z",
    ]
    payload["ranges"]["temperature"]["shape"] = [3, 2, 2]
    payload["ranges"]["temperature"]["values"] = [
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
    request_callable = MagicMock(return_value=make_response(payload))

    axes = discover_axes(
        _make_metadata(),
        mode="probe",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
        user_datetime="2025-01-01T00:00:00Z/2025-01-03T00:00:00Z",
    )

    assert request_callable.call_args.kwargs["params"]["datetime"] == (
        "2025-01-01T00:00:00Z/2025-01-03T00:00:00Z"
    )
    assert np.array_equal(
        axes[0].values,
        np.array(
            [
                "2025-01-01T00:00:00",
                "2025-01-02T00:00:00",
                "2025-01-03T00:00:00",
            ],
            dtype="datetime64[ns]",
        ),
    )


def test_probe_mode_uses_user_z_when_supplied(sample_cov_grid_4d: dict[str, Any]) -> None:
    payload = copy.deepcopy(sample_cov_grid_4d)
    payload["domain"]["axes"]["z"]["values"] = [850.0]
    payload["ranges"]["temperature"]["shape"] = [1, 1, 2, 2]
    payload["ranges"]["temperature"]["values"] = [273.15, 274.15, 275.15, 276.15]
    request_callable = MagicMock(return_value=make_response(payload))

    axes = discover_axes(
        _make_metadata(with_vertical=True),
        mode="probe",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
        user_z=850.0,
    )

    assert request_callable.call_args.kwargs["params"]["z"] == "850.0"
    assert np.allclose(axes[1].values, [850.0])


def test_probe_mode_routes_parsing_through_callable(
    sample_cov_grid_3d: dict[str, Any],
) -> None:
    request_callable = MagicMock(return_value=make_response(sample_cov_grid_3d))
    parse_coverage_callable = MagicMock(return_value=parse_coverage(sample_cov_grid_3d))

    discover_axes(
        _make_metadata(),
        mode="probe",
        request_callable=request_callable,
        parse_coverage_callable=parse_coverage_callable,
        cube_url="http://test/cube",
        instance=None,
    )

    parse_coverage_callable.assert_called_once_with(sample_cov_grid_3d)


def test_probe_mode_server_error_propagates() -> None:
    request_callable = MagicMock(side_effect=EdrServerError("down"))

    with pytest.raises(EdrServerError, match="down"):
        discover_axes(
            _make_metadata(),
            mode="probe",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )


def test_probe_mode_non_grid_domain_raises() -> None:
    sample_cov_pointseries = _load_payload("cov_pointseries.json")
    request_callable = MagicMock(return_value=make_response(sample_cov_pointseries))

    with pytest.raises(EdrUnsupportedFeatureError):
        discover_axes(
            _make_metadata(),
            mode="probe",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )


def test_probe_mode_bad_json_raises_coverage_error() -> None:
    request_callable = MagicMock(return_value=httpx.Response(200, content=b"not-json"))

    with pytest.raises(EdrCoverageJsonError, match="valid JSON"):
        discover_axes(
            _make_metadata(),
            mode="probe",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )


def test_probe_mode_non_object_json_raises_coverage_error() -> None:
    request_callable = MagicMock(return_value=httpx.Response(200, json=["not", "object"]))

    with pytest.raises(EdrCoverageJsonError, match="JSON object"):
        discover_axes(
            _make_metadata(),
            mode="probe",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )


def test_probe_mode_requires_temporal_extent(sample_cov_grid_3d: dict[str, Any]) -> None:
    request_callable = MagicMock(return_value=make_response(sample_cov_grid_3d))

    with pytest.raises(EdrMetadataError, match="temporal extent"):
        discover_axes(
            _make_metadata(with_temporal=False),
            mode="probe",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )


def test_metadata_only_does_not_call_transport() -> None:
    request_callable = MagicMock()

    axes = discover_axes(
        _make_metadata(),
        mode="metadata_only",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
    )

    assert [(axis.name, axis.kind) for axis in axes] == [("t", "t"), ("y", "y"), ("x", "x")]
    assert np.array_equal(axes[0].values, np.array(["2025-01-01T00:00:00"], dtype="datetime64[ns]"))
    request_callable.assert_not_called()


def test_metadata_only_without_temporal_values_uses_interval() -> None:
    axes = discover_axes(
        _make_metadata(with_temporal_values=False),
        mode="metadata_only",
        request_callable=MagicMock(),
        cube_url="http://test/cube",
        instance=None,
    )

    assert np.array_equal(
        axes[0].values,
        np.array(["2025-01-01T00:00:00", "2025-01-02T00:00:00"], dtype="datetime64[ns]"),
    )


def test_metadata_only_4d_includes_vertical_axis() -> None:
    axes = discover_axes(
        _make_metadata(with_vertical=True),
        mode="metadata_only",
        request_callable=MagicMock(),
        cube_url="http://test/cube",
        instance=None,
    )

    assert [(axis.name, axis.kind) for axis in axes] == [
        ("t", "t"),
        ("z", "z"),
        ("y", "y"),
        ("x", "x"),
    ]
    assert np.allclose(axes[1].values, [1000.0, 850.0])


def test_metadata_only_vertical_without_values_uses_interval() -> None:
    axes = discover_axes(
        _make_metadata(with_vertical=True, with_vertical_values=False),
        mode="metadata_only",
        request_callable=MagicMock(),
        cube_url="http://test/cube",
        instance=None,
    )

    assert np.allclose(axes[1].values, [500.0, 1000.0])


def test_metadata_only_without_temporal_extent_returns_spatial_only() -> None:
    axes = discover_axes(
        _make_metadata(with_temporal=False),
        mode="metadata_only",
        request_callable=MagicMock(),
        cube_url="http://test/cube",
        instance=None,
    )

    assert [(axis.name, axis.kind) for axis in axes] == [("y", "y"), ("x", "x")]


def test_strict_mode_raises_when_no_explicit_coord_values() -> None:
    request_callable = MagicMock()

    with pytest.raises(EdrMetadataError, match="explicit temporal coordinate values"):
        discover_axes(
            _make_metadata(with_temporal_values=False),
            mode="strict",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )
    request_callable.assert_not_called()


def test_strict_mode_raises_when_vertical_values_are_missing() -> None:
    request_callable = MagicMock()

    with pytest.raises(EdrMetadataError, match="explicit vertical coordinate values"):
        discover_axes(
            _make_metadata(with_vertical=True, with_vertical_values=False),
            mode="strict",
            request_callable=request_callable,
            cube_url="http://test/cube",
            instance=None,
        )
    request_callable.assert_not_called()


def test_strict_mode_succeeds_with_required_explicit_values() -> None:
    request_callable = MagicMock()

    axes = discover_axes(
        _make_metadata(with_vertical=True),
        mode="strict",
        request_callable=request_callable,
        cube_url="http://test/cube",
        instance=None,
    )

    assert [(axis.name, axis.kind) for axis in axes] == [
        ("t", "t"),
        ("z", "z"),
        ("y", "y"),
        ("x", "x"),
    ]
    request_callable.assert_not_called()


def test_invalid_discovery_mode_raises() -> None:
    with pytest.raises(ValueError, match="invalid discovery mode"):
        discover_axes(
            _make_metadata(),
            mode="surprise",
            request_callable=MagicMock(),
            cube_url="http://test/cube",
            instance=None,
        )


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("x", "x"),
        ("lon", "x"),
        ("longitude", "x"),
        ("y", "y"),
        ("lat", "y"),
        ("latitude", "y"),
        ("z", "z"),
        ("level", "z"),
        ("pressure", "z"),
        ("height", "z"),
        ("depth", "z"),
        ("t", "t"),
        ("time", "t"),
    ],
)
def test_axis_kind_classifies_x_y_z_t(name: str, kind: str) -> None:
    assert axis_kind(name) == kind


def test_axis_kind_case_insensitive() -> None:
    assert axis_kind("LONGITUDE") == "x"
    assert axis_kind("LAT") == "y"


def test_axis_kind_unknown_raises() -> None:
    with pytest.raises(EdrCoverageJsonError, match="foo"):
        axis_kind("foo")
