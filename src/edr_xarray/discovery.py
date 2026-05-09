"""Coordinate axis discovery strategies for EDR collections.

Three modes:
- 'probe': issues one HTTP request to discover full grid axes
- 'metadata_only': uses only collection metadata (bbox/temporal values)
- 'strict': requires explicit temporal/vertical coordinate values in metadata

All are pure except 'probe' mode which calls request_callable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, Literal, cast

import httpx
import numpy as np

from edr_xarray.coveragejson import CoverageData, parse_coverage
from edr_xarray.errors import EdrCoverageJsonError, EdrMetadataError
from edr_xarray.indexer import AxisInfo
from edr_xarray.metadata import CollectionMetadata, TemporalExtent
from edr_xarray.query import encode_bbox, encode_datetime

__all__ = [
    "DiscoveryMode",
    "ParseCoverageCallable",
    "RequestCallable",
    "axis_kind",
    "discover_axes",
    "validate_discovery_mode",
]

DiscoveryMode = Literal["probe", "metadata_only", "strict"]
DISCOVERY_MODES: Final = frozenset(("probe", "metadata_only", "strict"))
RequestCallable = Callable[..., httpx.Response]
ParseCoverageCallable = Callable[[dict[str, Any]], CoverageData]
AxisKind = Literal["x", "y", "z", "t"]


def axis_kind(name: str) -> AxisKind:
    """Classify an EDR/CoverageJSON axis name as x, y, z, or t."""
    normalized = name.lower()
    if normalized in {"x", "lon", "longitude"}:
        return "x"
    if normalized in {"y", "lat", "latitude"}:
        return "y"
    if normalized in {"z", "level", "pressure", "height", "depth"}:
        return "z"
    if normalized in {"t", "time"}:
        return "t"
    raise EdrCoverageJsonError(f"axis name '{name}' could not be classified as x/y/z/t")


def _datetime64_values(values: tuple[str, ...]) -> np.ndarray[Any, np.dtype[np.datetime64]]:
    stripped = tuple(value[:-1] if value.endswith("Z") else value for value in values)
    return np.array(stripped, dtype="datetime64[ns]")


def _metadata_axes(metadata: CollectionMetadata) -> tuple[AxisInfo, ...]:
    axes: list[AxisInfo] = []
    temporal = metadata.temporal
    if temporal is not None:
        if temporal.values is not None:
            time_values = _datetime64_values(temporal.values)
        else:
            time_values = _datetime64_values(temporal.interval)
        axes.append(AxisInfo(name="t", values=time_values, kind="t"))

    if metadata.vertical is not None:
        if metadata.vertical.values is not None:
            z_values = np.array(list(metadata.vertical.values))
        else:
            z_values = np.array([metadata.vertical.interval[0], metadata.vertical.interval[1]])
        axes.append(AxisInfo(name="z", values=z_values, kind="z"))

    lon_min, lat_min, lon_max, lat_max = metadata.spatial.bbox
    axes.append(AxisInfo(name="y", values=np.array([lat_min, lat_max]), kind="y"))
    axes.append(AxisInfo(name="x", values=np.array([lon_min, lon_max]), kind="x"))
    return tuple(axes)


def _require_temporal(metadata: CollectionMetadata) -> TemporalExtent:
    if metadata.temporal is None:
        raise EdrMetadataError("collection metadata must define temporal extent")
    return metadata.temporal


def validate_discovery_mode(mode: str) -> DiscoveryMode:
    """Return a validated discovery mode or raise a clear error."""
    if mode not in DISCOVERY_MODES:
        allowed = ", ".join(sorted(DISCOVERY_MODES))
        raise ValueError(f"invalid discovery mode {mode!r}; expected one of: {allowed}")
    return cast("DiscoveryMode", mode)


def _probe_axes(
    metadata: CollectionMetadata,
    request_callable: RequestCallable,
    parse_coverage_callable: ParseCoverageCallable,
    cube_url: str,
    user_bbox: tuple[float, float, float, float] | None = None,
) -> tuple[AxisInfo, ...]:
    temporal = _require_temporal(metadata)
    # Use the user's bbox if supplied so the discovered axes match what
    # subsequent .values fetches will return.  Without a user bbox, probe the
    # collection bbox because xarray requires fixed declared and returned shapes.
    probe_bbox = user_bbox if user_bbox is not None else metadata.spatial.bbox
    params = {
        "bbox": encode_bbox(probe_bbox),
        "datetime": encode_datetime(temporal.interval[0]),
        "parameter-name": next(iter(metadata.parameters.keys())),
        "f": "CoverageJSON",
    }
    response = request_callable("GET", cube_url, params=params)
    try:
        raw_payload = response.json()
    except ValueError as exc:
        raise EdrCoverageJsonError("CoverageJSON response body is not valid JSON") from exc
    if not isinstance(raw_payload, dict):
        raise EdrCoverageJsonError("CoverageJSON response body must be a JSON object")

    cov = parse_coverage_callable(cast("dict[str, Any]", raw_payload))
    axes = []
    for name in cov.axis_names:
        kind = axis_kind(name)
        values = (
            _datetime64_values(temporal.values)
            if kind == "t" and temporal.values is not None
            else cov.axes[name].values
        )
        axes.append(AxisInfo(name=name, values=values, kind=kind))
    return tuple(axes)


def discover_axes(
    metadata: CollectionMetadata,
    *,
    mode: str,
    request_callable: RequestCallable,
    parse_coverage_callable: ParseCoverageCallable = parse_coverage,
    cube_url: str,
    instance: str | None,
    user_bbox: tuple[float, float, float, float] | None = None,
) -> tuple[AxisInfo, ...]:
    """Discover collection axes using probe, metadata-only, or strict strategy."""
    del instance
    discovery_mode = validate_discovery_mode(mode)
    if discovery_mode == "probe":
        return _probe_axes(
            metadata,
            request_callable,
            parse_coverage_callable,
            cube_url,
            user_bbox=user_bbox,
        )
    if discovery_mode == "strict":
        temporal = metadata.temporal
        if temporal is None or temporal.values is None:
            raise EdrMetadataError(
                "strict mode requires explicit temporal coordinate values in metadata"
            )
        if metadata.vertical is not None and metadata.vertical.values is None:
            raise EdrMetadataError(
                "strict mode requires explicit vertical coordinate values in metadata"
            )
    return _metadata_axes(metadata)
