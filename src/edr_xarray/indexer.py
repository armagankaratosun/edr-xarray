"""Translate xarray BasicIndexer key tuples to EDR cube query parameters.

Pure functions — no I/O, no network, no global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from edr_xarray.query import encode_bbox, encode_datetime, encode_z

__all__ = ["AxisInfo", "slice_extent", "translate_indexer"]


@dataclass(frozen=True, eq=False)
class AxisInfo:
    """A discovered domain axis with its coordinate values and semantic kind."""

    name: str
    values: npt.NDArray[Any]
    kind: Literal["x", "y", "z", "t"]


def slice_extent(values: npt.NDArray[Any], idx: int | slice) -> tuple[Any, Any]:
    """Convert an int or slice index into the inclusive (lo, hi) coordinate pair."""
    if isinstance(idx, int):
        v = values[idx]
        return (v, v)

    n = len(values)
    positions = tuple(range(*idx.indices(n)))
    if not positions:
        raise ValueError("empty slice cannot be represented as an EDR query extent")
    return (values[positions[0]], values[positions[-1]])


def _is_full_extent(idx: int | slice, length: int) -> bool:
    if isinstance(idx, int):
        return False
    return tuple(range(*idx.indices(length))) == tuple(range(length))


def _format_datetime(t: Any) -> str:  # noqa: ANN401
    seconds = np.datetime64(t, "s")
    return str(np.datetime_as_string(seconds, unit="s", timezone="UTC"))


def _format_bbox(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> str:
    if lon_min == lon_max or lat_min == lat_max:
        return f"{lon_min},{lat_min},{lon_max},{lat_max}"
    return encode_bbox((lon_min, lat_min, lon_max, lat_max))


def _ordered_extent(extent: tuple[Any, Any]) -> tuple[float, float]:
    first = float(extent[0])
    last = float(extent[1])
    return (min(first, last), max(first, last))


def translate_indexer(
    key: tuple[int | slice, ...],
    axes: tuple[AxisInfo, ...],
) -> dict[str, str]:
    """Translate a basic indexer key tuple into EDR cube query parameters."""
    if len(key) != len(axes):
        raise ValueError(f"indexer length {len(key)} does not match axis count {len(axes)}")

    result: dict[str, str] = {}
    lon_extent: tuple[Any, Any] | None = None
    lat_extent: tuple[Any, Any] | None = None
    spatial_full = True

    for idx, axis in zip(key, axes, strict=True):
        n = len(axis.values)
        full = _is_full_extent(idx, n)

        if axis.kind == "x":
            lon_extent = slice_extent(axis.values, idx)
            if not full:
                spatial_full = False
        elif axis.kind == "y":
            lat_extent = slice_extent(axis.values, idx)
            if not full:
                spatial_full = False
        elif axis.kind == "z":
            if full:
                continue
            lo, hi = slice_extent(axis.values, idx)
            z_val = str(float(lo)) if lo == hi else f"{float(lo)}/{float(hi)}"
            encoded_z = encode_z(z_val)
            assert encoded_z is not None
            result["z"] = encoded_z
        elif axis.kind == "t":
            if full:
                continue
            t_lo, t_hi = slice_extent(axis.values, idx)
            iso_lo = _format_datetime(t_lo)
            iso_hi = _format_datetime(t_hi)
            dt_val = iso_lo if iso_lo == iso_hi else f"{iso_lo}/{iso_hi}"
            encoded_dt = encode_datetime(dt_val)
            assert encoded_dt is not None
            result["datetime"] = encoded_dt

    if not spatial_full and lon_extent is not None and lat_extent is not None:
        lon_min, lon_max = _ordered_extent(lon_extent)
        lat_min, lat_max = _ordered_extent(lat_extent)
        result["bbox"] = _format_bbox(
            lon_min,
            lat_min,
            lon_max,
            lat_max,
        )

    return result
