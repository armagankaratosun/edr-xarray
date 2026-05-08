"""Query parameter encoders and validators for OGC EDR cube queries.

All functions are pure: no I/O, no network calls, no global state.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from edr_xarray.errors import EdrUnsupportedFeatureError

__all__ = [
    "encode_bbox",
    "encode_crs",
    "encode_datetime",
    "encode_parameter_names",
    "encode_z",
    "negotiate_format",
]

_ISO_INSTANT_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z"
)


def _is_iso_instant(value: str) -> bool:
    return bool(_ISO_INSTANT_RE.fullmatch(value))


def encode_bbox(bbox: Sequence[float]) -> str:
    """Validate a CRS84 bbox and serialize it as a comma-separated string."""
    lon_min, lat_min, lon_max, lat_max = bbox

    if lat_min < -90 or lat_max > 90:
        raise ValueError("latitude values must be in [-90, 90]")
    if lon_min < -180 or lon_max > 180:
        raise ValueError("longitude values must be in [-180, 180]")
    if lon_min >= lon_max:
        raise EdrUnsupportedFeatureError(
            "antimeridian-crossing bbox not supported in v1; lon_min must be < lon_max"
        )
    if lat_min >= lat_max:
        raise ValueError("lat_min must be less than lat_max")

    return f"{lon_min},{lat_min},{lon_max},{lat_max}"


def encode_datetime(dt: str | None) -> str | None:
    """Validate an ISO instant or closed interval and return it unchanged."""
    if dt is None:
        return None

    if ".." in dt:
        raise EdrUnsupportedFeatureError("open datetime intervals not supported in v1")

    if "/" in dt:
        parts = dt.split("/")
        if len(parts) != 2 or not all(_is_iso_instant(part) for part in parts):
            raise ValueError(
                "datetime must be an ISO 8601 instant (e.g. "
                "2025-01-01T00:00:00Z) or interval (start/end)"
            )
        return dt

    if not _is_iso_instant(dt):
        raise ValueError(
            "datetime must be an ISO 8601 instant (e.g. "
            "2025-01-01T00:00:00Z) or interval (start/end)"
        )

    return dt


def encode_z(z: float | int | str | None) -> str | None:
    """Validate a scalar z value or a closed range string."""
    if z is None:
        return None

    if isinstance(z, (int, float)):
        return str(z)

    if z.startswith("R"):
        raise EdrUnsupportedFeatureError("z repeat syntax (R...) not supported in v1")

    if "," in z:
        raise EdrUnsupportedFeatureError("z multi-level lists not supported in v1")

    if z.count("/") == 1:
        lo, hi = z.split("/")
        try:
            float(lo)
            float(hi)
        except ValueError as exc:
            raise ValueError("z must be a numeric value or 'lo/hi' range string") from exc
        return z

    try:
        float(z)
    except ValueError as exc:
        raise ValueError("z must be a numeric value or 'lo/hi' range string") from exc

    return z


def encode_parameter_names(names: list[str] | None) -> str | None:
    """Validate a non-empty parameter name list and join it for the query."""
    if names is None:
        return None
    if not names:
        raise ValueError("parameter_names must be None or a non-empty list")
    return ",".join(names)


def encode_crs(crs: str | None, allowed: tuple[str, ...]) -> str | None:
    """Validate that a CRS is advertised by the collection."""
    if crs is None:
        return None
    if crs not in allowed:
        raise EdrUnsupportedFeatureError(
            f"crs '{crs}' not in collection's advertised CRS list {allowed}"
        )
    return crs


def negotiate_format(advertised: tuple[str, ...]) -> str:
    """Select CoverageJSON when the server advertises it."""
    if any(value.lower() == "coveragejson" for value in advertised):
        return "CoverageJSON"
    raise EdrUnsupportedFeatureError(
        f"server does not advertise CoverageJSON; advertised formats: {advertised}"
    )
