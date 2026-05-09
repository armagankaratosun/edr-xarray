"""Parser for OGC EDR collection metadata.

All functions are pure: no I/O, no logging, no global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from edr_xarray.errors import EdrMetadataError

__all__ = [
    "CollectionMetadata",
    "CubeLink",
    "ParameterDefinition",
    "SpatialExtent",
    "TemporalExtent",
    "VerticalExtent",
    "cube_url",
    "parse_collection_metadata",
]


@dataclass(frozen=True)
class SpatialExtent:
    """Spatial bounding box with optional CRS identifier."""

    bbox: tuple[float, float, float, float]
    crs: str | None


@dataclass(frozen=True)
class TemporalExtent:
    """Temporal interval with optional discrete value list."""

    interval: tuple[str, str]
    values: tuple[str, ...] | None


@dataclass(frozen=True)
class VerticalExtent:
    """Vertical interval with optional discrete levels and vertical reference system."""

    interval: tuple[float, float]
    values: tuple[float, ...] | None
    vrs: str | None


@dataclass(frozen=True)
class ParameterDefinition:
    """Parameter (variable) advertised by an EDR collection."""

    id: str
    unit: str | None
    standard_name: str | None
    long_name: str | None
    cell_methods: str | None


@dataclass(frozen=True)
class CubeLink:
    """Resolved cube data-query link with negotiated formats and CRS options."""

    href: str
    output_formats: tuple[str, ...]
    default_output_format: str | None
    crs_options: tuple[str, ...]


@dataclass(frozen=True)
class CollectionMetadata:
    """Parsed view of an EDR collection's advertised metadata."""

    id: str
    title: str | None
    description: str | None
    spatial: SpatialExtent
    temporal: TemporalExtent | None
    vertical: VerticalExtent | None
    crs_options: tuple[str, ...]
    parameters: dict[str, ParameterDefinition]
    cube_link: CubeLink
    instances_link: str | None


def _parse_spatial(extent: dict[str, Any]) -> SpatialExtent:
    spatial = extent.get("spatial") or {}
    bbox_list = spatial.get("bbox")
    if not bbox_list:
        raise EdrMetadataError(
            "required field 'extent.spatial.bbox' missing in collection metadata"
        )
    if len(bbox_list) > 1:
        raise EdrMetadataError(
            "multiple disjoint bboxes in extent.spatial.bbox are not supported in v1"
        )
    raw = bbox_list[0]
    bbox = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return SpatialExtent(bbox=bbox, crs=spatial.get("crs"))


def _parse_temporal(extent: dict[str, Any]) -> TemporalExtent | None:
    temporal = extent.get("temporal")
    if not temporal:
        return None
    interval_list = temporal.get("interval", [])
    if not interval_list:
        return None
    raw = interval_list[0]
    interval = (str(raw[0]), str(raw[1]))
    raw_values = temporal.get("values") or []
    values = tuple(str(v) for v in raw_values) if raw_values else None
    return TemporalExtent(interval=interval, values=values)


def _parse_vertical(extent: dict[str, Any]) -> VerticalExtent | None:
    vertical = extent.get("vertical")
    if not vertical:
        return None
    interval_list = vertical.get("interval", [])
    if not interval_list:
        return None
    raw = interval_list[0]
    interval = (float(raw[0]), float(raw[1]))
    raw_values = vertical.get("values") or []
    values = tuple(float(v) for v in raw_values) if raw_values else None
    return VerticalExtent(interval=interval, values=values, vrs=vertical.get("vrs"))


def _parse_parameter(param_id: str, p: dict[str, Any]) -> ParameterDefinition:
    unit = p.get("unit", {}).get("symbol", {}).get("value")
    observed = p.get("observedProperty", {})
    standard_name = observed.get("id") if observed else None
    long_name = observed.get("label", {}).get("en") if observed else None
    cell_methods = p.get("measurementType", {}).get("method")
    return ParameterDefinition(
        id=param_id,
        unit=unit,
        standard_name=standard_name,
        long_name=long_name,
        cell_methods=cell_methods,
    )


def _parse_cube_link(payload: dict[str, Any]) -> CubeLink:
    cube = payload.get("data_queries", {}).get("cube", {}).get("link")
    if not cube or not cube.get("href"):
        raise EdrMetadataError(
            "required field 'data_queries.cube.link.href' missing in collection metadata"
        )
    href = cube["href"]
    variables = cube.get("variables", {}) or {}
    output_formats = tuple(variables.get("output_formats") or payload.get("output_formats") or [])
    default_output_format = variables.get("default_output_format")
    crs_options = tuple(d["crs"] for d in variables.get("crs_details", []) if "crs" in d)
    return CubeLink(
        href=href,
        output_formats=output_formats,
        default_output_format=default_output_format,
        crs_options=crs_options,
    )


def parse_collection_metadata(payload: dict[str, Any]) -> CollectionMetadata:
    """Parse an OGC EDR collection metadata document into ``CollectionMetadata``.

    Raises ``EdrMetadataError`` when required fields are missing or malformed.
    """
    if "id" not in payload:
        raise EdrMetadataError("required field 'id' missing in collection metadata")
    if "parameter_names" not in payload:
        raise EdrMetadataError("required field 'parameter_names' missing in collection metadata")

    extent = payload.get("extent")
    if not extent:
        raise EdrMetadataError("required field 'extent' missing in collection metadata")
    spatial = _parse_spatial(extent)
    temporal = _parse_temporal(extent)
    vertical = _parse_vertical(extent)

    parameters = {
        param_id: _parse_parameter(param_id, p)
        for param_id, p in payload["parameter_names"].items()
    }

    cube_link = _parse_cube_link(payload)
    instances_link = (
        payload.get("data_queries", {}).get("instances", {}).get("link", {}).get("href")
    )

    return CollectionMetadata(
        id=payload["id"],
        title=payload.get("title"),
        description=payload.get("description"),
        spatial=spatial,
        temporal=temporal,
        vertical=vertical,
        crs_options=tuple(payload.get("crs", [])),
        parameters=parameters,
        cube_link=cube_link,
        instances_link=instances_link,
    )


def _ensure_absolute(href: str, base_url: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))


def cube_url(metadata: CollectionMetadata, instance: str | None, base_url: str) -> str:
    """Return the absolute cube-query URL, optionally rewritten for a named instance.

    When ``instance`` is None, the canonical ``cube_link.href`` is returned (resolved
    against ``base_url`` if relative). When ``instance`` is provided, the trailing
    ``/cube`` segment is replaced with ``/instances/<instance>/cube``; raise
    ``EdrMetadataError`` if the href does not follow that shape.
    """
    href = _ensure_absolute(metadata.cube_link.href, base_url)
    if instance is None:
        return href
    if not href.endswith("/cube"):
        raise EdrMetadataError(
            "cannot resolve instance cube URL from href — non-standard URL shape; "
            "subclass _build_cube_url to override"
        )
    return href[: -len("/cube")] + f"/instances/{instance}/cube"
