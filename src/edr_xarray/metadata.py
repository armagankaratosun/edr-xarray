"""Parser for OGC EDR collection metadata.

All functions are pure: no I/O, no logging, no global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

from edr_xarray.errors import EdrMetadataError

__all__ = [
    "CollectionMetadata",
    "CubeLink",
    "ParameterDefinition",
    "SpatialExtent",
    "TemporalExtent",
    "VerticalExtent",
    "cube_url",
    "instance_metadata_url",
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
    spatial = extent.get("spatial")
    if not isinstance(spatial, dict):
        raise EdrMetadataError(
            "required field 'extent.spatial.bbox' missing in collection metadata"
        )
    bbox_list = spatial.get("bbox")
    if not isinstance(bbox_list, list) or not bbox_list:
        raise EdrMetadataError(
            "required field 'extent.spatial.bbox' missing in collection metadata"
        )
    if len(bbox_list) > 1:
        raise EdrMetadataError(
            "multiple disjoint bboxes in extent.spatial.bbox are not supported in v1"
        )
    raw = bbox_list[0]
    if not isinstance(raw, list) or len(raw) < 4:
        raise EdrMetadataError("extent.spatial.bbox[0] must contain four coordinates")
    try:
        bbox = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError) as exc:
        raise EdrMetadataError("extent.spatial.bbox[0] contains non-numeric values") from exc
    return SpatialExtent(bbox=bbox, crs=spatial.get("crs"))


def _parse_temporal(extent: dict[str, Any]) -> TemporalExtent | None:
    temporal = extent.get("temporal")
    if temporal is None:
        return None
    if not isinstance(temporal, dict):
        raise EdrMetadataError("extent.temporal must be an object")
    if not temporal:
        return None
    interval_list = temporal.get("interval", [])
    if not interval_list:
        return None
    if not isinstance(interval_list, list):
        raise EdrMetadataError("extent.temporal.interval must be an array")
    raw = interval_list[0]
    if not isinstance(raw, list) or len(raw) < 2:
        raise EdrMetadataError("extent.temporal.interval[0] must contain start and end")
    interval = (str(raw[0]), str(raw[1]))
    raw_values = temporal.get("values") or []
    if raw_values and not isinstance(raw_values, list):
        raise EdrMetadataError("extent.temporal.values must be an array")
    values = tuple(str(v) for v in raw_values) if raw_values else None
    return TemporalExtent(interval=interval, values=values)


def _parse_vertical(extent: dict[str, Any]) -> VerticalExtent | None:
    vertical = extent.get("vertical")
    if vertical is None:
        return None
    if not isinstance(vertical, dict):
        raise EdrMetadataError("extent.vertical must be an object")
    if not vertical:
        return None
    interval_list = vertical.get("interval", [])
    if not interval_list:
        return None
    if not isinstance(interval_list, list):
        raise EdrMetadataError("extent.vertical.interval must be an array")
    raw = interval_list[0]
    if not isinstance(raw, list) or len(raw) < 2:
        raise EdrMetadataError("extent.vertical.interval[0] must contain lower and upper")
    try:
        interval = (float(raw[0]), float(raw[1]))
    except (TypeError, ValueError) as exc:
        raise EdrMetadataError("extent.vertical.interval[0] contains non-numeric values") from exc
    raw_values = vertical.get("values") or []
    if raw_values and not isinstance(raw_values, list):
        raise EdrMetadataError("extent.vertical.values must be an array")
    try:
        values = tuple(float(v) for v in raw_values) if raw_values else None
    except (TypeError, ValueError) as exc:
        raise EdrMetadataError("extent.vertical.values contains non-numeric values") from exc
    return VerticalExtent(interval=interval, values=values, vrs=vertical.get("vrs"))


def _nested_str(spec: dict[str, Any], *path: str) -> str | None:
    current: Any = spec
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _parse_parameter(param_id: str, p: dict[str, Any]) -> ParameterDefinition:
    if not isinstance(p, dict):
        raise EdrMetadataError(f"parameter_names.{param_id} must be an object")
    return ParameterDefinition(
        id=param_id,
        unit=_nested_str(p, "unit", "symbol", "value"),
        standard_name=_nested_str(p, "observedProperty", "id"),
        long_name=_nested_str(p, "observedProperty", "label", "en"),
        cell_methods=_nested_str(p, "measurementType", "method"),
    )


def _parse_cube_link(payload: dict[str, Any]) -> CubeLink:
    data_queries = payload.get("data_queries")
    if not isinstance(data_queries, dict):
        data_queries = {}
    cube_query = data_queries.get("cube")
    if not isinstance(cube_query, dict):
        cube_query = {}
    cube = cube_query.get("link")
    if not isinstance(cube, dict) or not cube.get("href"):
        raise EdrMetadataError(
            "required field 'data_queries.cube.link.href' missing in collection metadata"
        )
    href = cube["href"]
    raw_variables = cube.get("variables")
    if raw_variables is None:
        variables: dict[str, Any] = {}
    elif not isinstance(raw_variables, dict):
        raise EdrMetadataError("data_queries.cube.link.variables must be an object")
    else:
        variables = raw_variables
    output_formats = tuple(variables.get("output_formats") or payload.get("output_formats") or [])
    default_output_format = variables.get("default_output_format")
    crs_details = variables.get("crs_details", [])
    if not isinstance(crs_details, list):
        raise EdrMetadataError("data_queries.cube.link.variables.crs_details must be an array")
    crs_options = tuple(d["crs"] for d in crs_details if isinstance(d, dict) and "crs" in d)
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
    if not isinstance(extent, dict):
        raise EdrMetadataError("required field 'extent' missing in collection metadata")
    spatial = _parse_spatial(extent)
    temporal = _parse_temporal(extent)
    vertical = _parse_vertical(extent)

    raw_parameters = payload["parameter_names"]
    if not isinstance(raw_parameters, dict):
        raise EdrMetadataError("parameter_names must be an object")
    parameters = {param_id: _parse_parameter(param_id, p) for param_id, p in raw_parameters.items()}

    cube_link = _parse_cube_link(payload)
    data_queries = payload.get("data_queries")
    instances_query = data_queries.get("instances") if isinstance(data_queries, dict) else None
    instances_link_payload = (
        instances_query.get("link") if isinstance(instances_query, dict) else None
    )
    instances_link = (
        instances_link_payload.get("href") if isinstance(instances_link_payload, dict) else None
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


def _quote_path_segment(value: str, field_name: str) -> str:
    if not value:
        raise EdrMetadataError(f"{field_name} must be a non-empty string")
    return quote(value, safe="")


def instance_metadata_url(
    metadata: CollectionMetadata,
    instance: str,
    *,
    base_url: str,
) -> str:
    """Return the absolute metadata URL for a named collection instance.

    Prefer the advertised ``data_queries.instances.link.href`` when present.
    When it is absent, fall back to the standard path below the collection
    resource URL.
    """
    encoded_instance = _quote_path_segment(instance, "instance")
    instances_href = metadata.instances_link or "instances"
    instances_url = _ensure_absolute(instances_href, base_url)
    return urljoin(instances_url.rstrip("/") + "/", encoded_instance)


def cube_url(metadata: CollectionMetadata, instance: str | None, base_url: str) -> str:
    """Return the absolute cube-query URL, optionally rewritten for a named instance.

    When ``instance`` is None, the canonical ``cube_link.href`` is returned (resolved
    against ``base_url`` if relative). When ``instance`` is provided, an already
    instance-specific cube link is returned unchanged; otherwise the trailing
    ``/cube`` segment is replaced with ``/instances/<instance>/cube``. Raise
    ``EdrMetadataError`` if the href does not follow either shape.
    """
    href = _ensure_absolute(metadata.cube_link.href, base_url)
    if instance is None:
        return href
    encoded_instance = _quote_path_segment(instance, "instance")
    normalized_href = href.rstrip("/")
    instance_suffix = f"/instances/{encoded_instance}/cube"
    if normalized_href.endswith(instance_suffix):
        return normalized_href
    if not normalized_href.endswith("/cube"):
        raise EdrMetadataError(
            "cannot resolve instance cube URL from href — non-standard URL shape; "
            "subclass _build_cube_url to override"
        )
    return normalized_href[: -len("/cube")] + instance_suffix
