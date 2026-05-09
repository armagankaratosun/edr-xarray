"""Build xr.Variable and coordinate dicts from EDR metadata and discovered axes.

All functions are pure with respect to network I/O.
Laziness invariant: make_backend_array is called but __getitem__ is NEVER called.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

import numpy as np
import xarray as xr
from xarray.backends import BackendArray
from xarray.core import indexing

from edr_xarray.indexer import AxisInfo
from edr_xarray.metadata import CollectionMetadata

__all__ = ["build_coord_variables", "build_data_variables", "build_global_attrs"]


class _ArrayLikeBackend(Protocol):
    @property
    def dtype(self) -> np.typing.DTypeLike: ...

    def __getitem__(self, key: indexing.ExplicitIndexer) -> np.typing.ArrayLike: ...


class _NdimBackendArray(BackendArray):
    """BackendArray adapter for array-likes that only expose shape and dtype."""

    def __init__(self, array: _ArrayLikeBackend, shape: tuple[int, ...]) -> None:
        self._array = array
        self._shape = shape

    @property
    def shape(self) -> tuple[int, ...]:
        """Return the backend shape without reading data."""
        return self._shape

    @property
    def dtype(self) -> np.typing.DTypeLike:
        """Return the backend dtype without reading data."""
        return self._array.dtype

    def __getitem__(self, key: indexing.ExplicitIndexer) -> np.typing.ArrayLike:
        """Delegate reads to the wrapped array when xarray eventually indexes it."""
        return self._array[key]


def _as_backend_array(array: BackendArray, shape: tuple[int, ...]) -> BackendArray:
    try:
        _ = array.ndim
    except AttributeError:
        return _NdimBackendArray(cast(_ArrayLikeBackend, array), shape)
    return array


def build_coord_variables(
    axes: tuple[AxisInfo, ...], metadata: CollectionMetadata
) -> dict[str, xr.Variable]:
    """Build one-dimensional coordinate variables for discovered axes."""
    coord_vars: dict[str, xr.Variable] = {}

    for axis in axes:
        attrs: dict[str, Any]
        if axis.kind == "x":
            attrs = {
                "axis": "X",
                "long_name": "longitude",
                "units": "degrees_east",
                "standard_name": "longitude",
            }
        elif axis.kind == "y":
            attrs = {
                "axis": "Y",
                "long_name": "latitude",
                "units": "degrees_north",
                "standard_name": "latitude",
            }
        elif axis.kind == "z":
            attrs = {
                "axis": "Z",
                "long_name": "vertical",
                "units": (
                    metadata.vertical.vrs if metadata.vertical and metadata.vertical.vrs else ""
                ),
            }
        else:
            attrs = {"axis": "T", "long_name": "time", "standard_name": "time"}

        coord_vars[axis.name] = xr.Variable(
            dims=(axis.name,), data=np.asarray(axis.values), attrs=attrs
        )

    return coord_vars


def build_data_variables(
    metadata: CollectionMetadata,
    axes: tuple[AxisInfo, ...],
    make_backend_array: Callable[[str, tuple[int, ...]], BackendArray],
) -> dict[str, xr.Variable]:
    """Build lazily indexed data variables for every advertised EDR parameter."""
    # v1 assumes each parameter uses the same discovered axes and shape.
    shape = tuple(len(axis.values) for axis in axes)
    dims = tuple(axis.name for axis in axes)
    time_axis_name = next(
        (axis.name for axis in axes if axis.kind == "t" and len(axis.values) >= 4),
        None,
    )

    data_vars: dict[str, xr.Variable] = {}
    for param_id, param_def in metadata.parameters.items():
        attrs = {
            key: value
            for key, value in {
                "units": param_def.unit,
                "standard_name": param_def.standard_name,
                "long_name": param_def.long_name,
                "cell_methods": param_def.cell_methods,
            }.items()
            if value is not None
        }
        backend_array = _as_backend_array(make_backend_array(param_id, shape), shape)
        data = indexing.LazilyIndexedArray(backend_array)
        encoding = {"preferred_chunks": {time_axis_name: 1}} if time_axis_name is not None else {}
        data_vars[param_id] = xr.Variable(dims=dims, data=data, attrs=attrs, encoding=encoding)

    return data_vars


def build_global_attrs(metadata: CollectionMetadata) -> dict[str, Any]:
    """Build CF-conventional global attributes from collection metadata."""
    attrs: dict[str, Any] = {"Conventions": "CF-1.10"}
    if metadata.title is not None:
        attrs["title"] = metadata.title
    if metadata.description is not None:
        attrs["summary"] = metadata.description
    return attrs
