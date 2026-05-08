"""Tests for edr_xarray.query — query parameter encoders and validators."""

# pyright: reportMissingImports=false
# ruff: noqa: D103

from __future__ import annotations

import pytest

from edr_xarray.errors import EdrUnsupportedFeatureError
from edr_xarray.query import (
    encode_bbox,
    encode_crs,
    encode_datetime,
    encode_parameter_names,
    encode_z,
    negotiate_format,
)


def test_encode_bbox_happy() -> None:
    assert encode_bbox((10.0, 40.0, 11.0, 41.0)) == "10.0,40.0,11.0,41.0"


def test_encode_bbox_list_input() -> None:
    assert encode_bbox([10, 40, 11, 41]) == "10,40,11,41"


def test_encode_bbox_antimeridian_raises() -> None:
    with pytest.raises(EdrUnsupportedFeatureError, match="antimeridian"):
        encode_bbox((170, 0, -170, 1))


def test_encode_bbox_invalid_lat_range() -> None:
    with pytest.raises(ValueError, match="latitude values"):
        encode_bbox((0, 100, 1, 101))


def test_encode_bbox_invalid_lon_range() -> None:
    with pytest.raises(ValueError, match="longitude values"):
        encode_bbox((-200, 0, -190, 1))


def test_encode_bbox_lat_min_ge_lat_max_raises() -> None:
    with pytest.raises(ValueError, match="lat_min"):
        encode_bbox((0, 41, 1, 40))


def test_encode_datetime_instant() -> None:
    assert encode_datetime("2025-01-01T00:00:00Z") == "2025-01-01T00:00:00Z"


def test_encode_datetime_interval() -> None:
    value = "2025-01-01T00:00:00Z/2025-01-02T00:00:00Z"
    assert encode_datetime(value) == value


def test_encode_datetime_none() -> None:
    assert encode_datetime(None) is None


def test_encode_datetime_open_interval_raises() -> None:
    with pytest.raises(EdrUnsupportedFeatureError, match="open datetime intervals"):
        encode_datetime("../2025-01-02T00:00:00Z")


def test_encode_datetime_malformed_raises() -> None:
    with pytest.raises(ValueError, match="datetime must be an ISO 8601 instant"):
        encode_datetime("yesterday")


def test_encode_datetime_malformed_interval_part_raises() -> None:
    with pytest.raises(ValueError, match="datetime must be an ISO 8601 instant"):
        encode_datetime("2025-01-01T00:00:00Z/not-an-instant")


def test_encode_z_scalar_int() -> None:
    assert encode_z(500) == "500"


def test_encode_z_scalar_float() -> None:
    assert encode_z(500.5) == "500.5"


def test_encode_z_range() -> None:
    assert encode_z("1000/300") == "1000/300"


def test_encode_z_repeat_syntax_raises() -> None:
    with pytest.raises(EdrUnsupportedFeatureError, match="repeat"):
        encode_z("R14/1000/-50")


def test_encode_z_list_raises() -> None:
    with pytest.raises(EdrUnsupportedFeatureError, match="multi-level"):
        encode_z("500,400,300")


def test_encode_z_none() -> None:
    assert encode_z(None) is None


def test_encode_z_invalid_string_raises() -> None:
    with pytest.raises(ValueError, match="numeric value"):
        encode_z("abc")


def test_encode_z_invalid_range_raises() -> None:
    with pytest.raises(ValueError, match="numeric value"):
        encode_z("1000/abc")


def test_encode_parameter_names_happy() -> None:
    assert encode_parameter_names(["t", "w"]) == "t,w"


def test_encode_parameter_names_none() -> None:
    assert encode_parameter_names(None) is None


def test_encode_parameter_names_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        encode_parameter_names([])


def test_encode_crs_allowed() -> None:
    assert encode_crs("CRS84", ("CRS84", "EPSG:4326")) == "CRS84"


def test_encode_crs_not_allowed_raises() -> None:
    with pytest.raises(EdrUnsupportedFeatureError, match="not in collection's advertised CRS list"):
        encode_crs("EPSG:3857", ("CRS84",))


def test_encode_crs_none() -> None:
    assert encode_crs(None, ("CRS84",)) is None


def test_negotiate_format_happy() -> None:
    assert negotiate_format(("CoverageJSON", "GeoJSON")) == "CoverageJSON"


def test_negotiate_format_case_insensitive() -> None:
    assert negotiate_format(("coveragejson",)) == "CoverageJSON"


def test_negotiate_format_no_match_raises() -> None:
    with pytest.raises(EdrUnsupportedFeatureError, match="does not advertise CoverageJSON"):
        negotiate_format(("GeoJSON",))
