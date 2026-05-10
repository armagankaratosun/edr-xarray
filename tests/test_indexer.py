"""Tests for edr_xarray.indexer — translate xarray indexer keys to EDR query params."""

# ruff: noqa: D103

from __future__ import annotations

import numpy as np
import pytest

from edr_xarray.indexer import AxisInfo, slice_extent, translate_indexer


def _time_axis(n: int = 3) -> AxisInfo:
    values = np.array(
        [f"2025-01-0{i + 1}T00:00:00" for i in range(n)],
        dtype="datetime64[ns]",
    )
    return AxisInfo(name="time", values=values, kind="t")


def _z_axis() -> AxisInfo:
    return AxisInfo(name="z", values=np.array([1000.0, 850.0, 500.0]), kind="z")


def _y_axis(n: int = 3) -> AxisInfo:
    return AxisInfo(name="y", values=np.array([40.0 + i for i in range(n)]), kind="y")


def _x_axis(n: int = 3) -> AxisInfo:
    return AxisInfo(name="x", values=np.array([10.0 + i for i in range(n)]), kind="x")


def test_slice_extent_int_returns_single_value() -> None:
    values = np.array([10.0, 11.0, 12.0])
    assert slice_extent(values, 1) == (11.0, 11.0)


def test_slice_extent_negative_int() -> None:
    values = np.array([10.0, 11.0, 12.0])
    assert slice_extent(values, -1) == (12.0, 12.0)


def test_slice_extent_full_slice_returns_first_last() -> None:
    values = np.array([10.0, 11.0, 12.0])
    assert slice_extent(values, slice(None)) == (10.0, 12.0)


def test_slice_extent_slice_with_start_stop() -> None:
    values = np.array([10.0, 11.0, 12.0, 13.0])
    assert slice_extent(values, slice(1, 3)) == (11.0, 12.0)


def test_slice_extent_slice_step_uses_selected_first_last() -> None:
    values = np.array([10.0, 11.0, 12.0])
    assert slice_extent(values, slice(0, 3, 2)) == (10.0, 12.0)


def test_slice_extent_empty_slice_raises() -> None:
    values = np.array([10.0, 11.0, 12.0])
    with pytest.raises(ValueError, match="empty slice"):
        slice_extent(values, slice(0, 0))


def test_full_slice_returns_empty_dict() -> None:
    axes = (_time_axis(), _y_axis(), _x_axis())
    key = (slice(None), slice(None), slice(None))
    assert translate_indexer(key, axes) == {}


def test_x_subset_produces_bbox() -> None:
    axes = (_y_axis(3), _x_axis(3))
    key = (slice(None), slice(1, 3))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "11.0,40.0,12.0,42.0"}


def test_y_subset_produces_bbox() -> None:
    axes = (_y_axis(3), _x_axis(3))
    key = (slice(0, 2), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "10.0,40.0,12.0,41.0"}


def test_xy_both_subset() -> None:
    axes = (_y_axis(3), _x_axis(3))
    key = (slice(0, 2), slice(1, 3))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "11.0,40.0,12.0,41.0"}


def test_z_int_produces_z_param() -> None:
    axes = (_z_axis(), _y_axis(), _x_axis())
    key = (1, slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"z": "850.0"}


def test_z_slice_produces_range() -> None:
    axes = (_z_axis(), _y_axis(), _x_axis())
    key = (slice(0, 2), slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"z": "1000.0/850.0"}


def test_time_int_produces_single_datetime() -> None:
    axes = (_time_axis(3), _y_axis(), _x_axis())
    key = (0, slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"datetime": "2025-01-01T00:00:00Z"}


def test_time_slice_produces_interval() -> None:
    axes = (_time_axis(3), _y_axis(), _x_axis())
    key = (slice(0, 2), slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"datetime": "2025-01-01T00:00:00Z/2025-01-02T00:00:00Z"}


def test_key_length_mismatch_raises() -> None:
    axes = (_y_axis(), _x_axis())
    with pytest.raises(ValueError, match="does not match axis count"):
        translate_indexer((slice(None),), axes)


def test_negative_index_on_z() -> None:
    axes = (_z_axis(), _y_axis(), _x_axis())
    key = (-1, slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"z": "500.0"}


def test_full_xyz_slice_produces_empty() -> None:
    axes = (_z_axis(), _y_axis(), _x_axis())
    key = (slice(None), slice(None), slice(None))
    assert translate_indexer(key, axes) == {}


def test_4d_partial_subset() -> None:
    axes = (_time_axis(3), _z_axis(), _y_axis(3), _x_axis(3))
    key = (slice(0, 2), 1, slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result["z"] == "850.0"
    assert result["datetime"] == "2025-01-01T00:00:00Z/2025-01-02T00:00:00Z"
    assert "bbox" not in result


def test_x_int_produces_degenerate_bbox() -> None:
    axes = (_y_axis(3), _x_axis(3))
    key = (slice(None), 1)
    result = translate_indexer(key, axes)
    assert result == {"bbox": "11.0,40.0,11.0,42.0"}


def test_y_int_produces_degenerate_bbox() -> None:
    axes = (_y_axis(3), _x_axis(3))
    key = (1, slice(None))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "10.0,41.0,12.0,41.0"}


def test_full_extent_via_explicit_zero_to_n_slice() -> None:
    axes = (_z_axis(), _y_axis(), _x_axis())
    key = (slice(0, 3), slice(0, 3), slice(0, 3))
    assert translate_indexer(key, axes) == {}


def test_explicit_subslice_not_starting_at_zero() -> None:
    axes = (_z_axis(), _y_axis(), _x_axis())
    key = (slice(1, 3), slice(None), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"z": "850.0/500.0"}


def test_stepped_x_slice_produces_bbox_covering_selected_points() -> None:
    axes = (_y_axis(3), _x_axis(3))
    key = (slice(None), slice(0, 3, 2))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "10.0,40.0,12.0,42.0"}


def test_descending_latitude_slice_produces_ordered_bbox() -> None:
    axes = (
        AxisInfo(name="y", values=np.array([42.0, 41.0, 40.0]), kind="y"),
        _x_axis(3),
    )
    key = (slice(0, 2), slice(None))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "10.0,41.0,12.0,42.0"}


def test_descending_longitude_slice_produces_ordered_bbox() -> None:
    axes = (
        _y_axis(3),
        AxisInfo(name="x", values=np.array([12.0, 11.0, 10.0]), kind="x"),
    )
    key = (slice(None), slice(0, 2))
    result = translate_indexer(key, axes)
    assert result == {"bbox": "11.0,40.0,12.0,42.0"}
