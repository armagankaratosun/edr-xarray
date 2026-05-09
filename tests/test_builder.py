"""Tests for building xarray variables from EDR metadata."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

from typing import Any

import numpy as np
from xarray.backends import BackendArray
from xarray.core import indexing

from edr_xarray.builder import build_coord_variables, build_data_variables, build_global_attrs
from edr_xarray.indexer import AxisInfo
from edr_xarray.metadata import (
    CollectionMetadata,
    CubeLink,
    ParameterDefinition,
    SpatialExtent,
    TemporalExtent,
    VerticalExtent,
)


class FakeArray(BackendArray):
    call_count: int = 0

    def __init__(self, name: str, shape: tuple[int, ...]) -> None:
        self._name = name
        self._shape = shape
        self._dtype = np.dtype(np.float64)

    @property
    def shape(self) -> tuple[int, ...]:
        return self._shape

    @property
    def dtype(self) -> np.dtype[np.float64]:
        return self._dtype

    def __getitem__(self, key: indexing.ExplicitIndexer) -> np.ndarray[Any, np.dtype[np.float64]]:
        FakeArray.call_count += 1
        return np.zeros(self.shape, dtype=self.dtype)


class PlainArray(BackendArray):
    call_count: int = 0

    def __init__(self, name: str, shape: tuple[int, ...]) -> None:
        self._name = name
        self._shape = shape
        self._dtype = np.dtype(np.float64)

    @property
    def shape(self) -> tuple[int, ...]:
        return self._shape

    @property
    def dtype(self) -> np.dtype[np.float64]:
        return self._dtype

    def __getitem__(self, key: indexing.ExplicitIndexer) -> np.ndarray[Any, np.dtype[np.float64]]:
        PlainArray.call_count += 1
        return np.ones(self.shape, dtype=self.dtype)


def _metadata(
    *,
    title: str | None = "Collection title",
    description: str | None = "Collection description",
    vertical: VerticalExtent | None = None,
    parameters: dict[str, ParameterDefinition] | None = None,
) -> CollectionMetadata:
    return CollectionMetadata(
        id="collection",
        title=title,
        description=description,
        spatial=SpatialExtent(bbox=(10.0, 40.0, 11.0, 41.0), crs=None),
        temporal=TemporalExtent(interval=("2025-01-01", "2025-01-05"), values=None),
        vertical=vertical,
        crs_options=("CRS84",),
        parameters=parameters
        or {
            "temp": ParameterDefinition(
                id="temp",
                unit="K",
                standard_name="air_temperature",
                long_name="Air Temperature",
                cell_methods="time: mean",
            )
        },
        cube_link=CubeLink(
            href="https://example.test/cube",
            output_formats=("CoverageJSON",),
            default_output_format="CoverageJSON",
            crs_options=("CRS84",),
        ),
        instances_link=None,
    )


def _x_axis(length: int = 3) -> AxisInfo:
    return AxisInfo(name="x", values=np.arange(length, dtype=float), kind="x")


def _y_axis(length: int = 2) -> AxisInfo:
    return AxisInfo(name="y", values=np.arange(length, dtype=float), kind="y")


def _z_axis(length: int = 2) -> AxisInfo:
    return AxisInfo(name="z", values=np.arange(length, dtype=float), kind="z")


def _time_axis(length: int = 3, name: str = "time") -> AxisInfo:
    values = np.array([f"2025-01-0{i + 1}T00:00:00" for i in range(length)], dtype="datetime64[ns]")
    return AxisInfo(name=name, values=values, kind="t")


def test_build_3d_coord_variables() -> None:
    coords = build_coord_variables((_x_axis(), _y_axis(), _time_axis()), _metadata())

    assert set(coords) == {"x", "y", "time"}
    assert coords["x"].attrs["axis"] == "X"
    assert coords["y"].attrs["axis"] == "Y"
    assert coords["time"].attrs["axis"] == "T"
    assert "units" not in coords["time"].attrs


def test_build_4d_coord_variables() -> None:
    metadata = _metadata(vertical=VerticalExtent(interval=(0.0, 1.0), values=None, vrs="m"))
    coords = build_coord_variables((_x_axis(), _y_axis(), _z_axis(), _time_axis()), metadata)

    assert set(coords) == {"x", "y", "z", "time"}
    assert coords["z"].attrs["axis"] == "Z"
    assert coords["z"].attrs["units"] == "m"


def test_z_coord_units_empty_without_vertical_reference() -> None:
    coords = build_coord_variables((_z_axis(),), _metadata())

    assert coords["z"].attrs["units"] == ""


def test_coord_variable_dims_match_axis_name() -> None:
    coords = build_coord_variables((_time_axis(name="valid_time"),), _metadata())

    assert coords["valid_time"].dims == ("valid_time",)


def test_data_variable_shape_matches_axes() -> None:
    axes = (_time_axis(4), _y_axis(2), _x_axis(3))
    data_vars = build_data_variables(_metadata(), axes, FakeArray)

    assert data_vars["temp"].shape == (4, 2, 3)
    assert data_vars["temp"].dims == ("time", "y", "x")


def test_data_variable_attrs_populated() -> None:
    data_vars = build_data_variables(_metadata(), (_y_axis(), _x_axis()), FakeArray)

    assert data_vars["temp"].attrs == {
        "units": "K",
        "standard_name": "air_temperature",
        "long_name": "Air Temperature",
        "cell_methods": "time: mean",
    }


def test_data_variable_attrs_drop_none() -> None:
    metadata = _metadata(
        parameters={
            "p": ParameterDefinition(
                id="p",
                unit=None,
                standard_name="air_temperature",
                long_name=None,
                cell_methods=None,
            )
        }
    )

    data_vars = build_data_variables(metadata, (_y_axis(), _x_axis()), FakeArray)

    assert "units" not in data_vars["p"].attrs
    assert data_vars["p"].attrs == {"standard_name": "air_temperature"}


def test_preferred_chunks_set_for_long_time_axis() -> None:
    axes = (_time_axis(5, name="valid_time"), _y_axis(), _x_axis())
    data_vars = build_data_variables(_metadata(), axes, FakeArray)

    assert data_vars["temp"].encoding["preferred_chunks"] == {"valid_time": 1}


def test_preferred_chunks_empty_for_short_time_axis() -> None:
    axes = (_time_axis(2), _y_axis(), _x_axis())
    data_vars = build_data_variables(_metadata(), axes, FakeArray)

    assert data_vars["temp"].encoding == {}


def test_preferred_chunks_empty_without_time_axis() -> None:
    data_vars = build_data_variables(_metadata(), (_y_axis(), _x_axis()), FakeArray)

    assert data_vars["temp"].encoding == {}


def test_laziness_no_getitem_during_build() -> None:
    FakeArray.call_count = 0

    build_data_variables(_metadata(), (_time_axis(5), _y_axis(), _x_axis()), FakeArray)

    assert FakeArray.call_count == 0


def test_plain_array_backend_is_lazy_until_read() -> None:
    PlainArray.call_count = 0
    data_vars = build_data_variables(_metadata(), (_y_axis(), _x_axis()), PlainArray)

    assert data_vars["temp"].shape == (2, 3)
    assert data_vars["temp"].dtype == np.dtype(np.float64)
    assert PlainArray.call_count == 0
    np.testing.assert_array_equal(data_vars["temp"].data, np.ones((2, 3)))
    assert PlainArray.call_count == 1


def test_global_attrs_conventions_always_present() -> None:
    attrs = build_global_attrs(_metadata(title=None, description=None))

    assert attrs["Conventions"] == "CF-1.10"


def test_global_attrs_populates_title() -> None:
    attrs = build_global_attrs(_metadata(title="title", description=None))

    assert attrs["title"] == "title"


def test_global_attrs_drops_none_title() -> None:
    attrs = build_global_attrs(_metadata(title=None, description="description"))

    assert "title" not in attrs
    assert attrs["summary"] == "description"
