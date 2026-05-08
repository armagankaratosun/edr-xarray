"""CoverageJSON parser for EDR Grid responses.

Only supports domainType='Grid' with NdArray ranges.
All functions are pure: no I/O, no logging, no global state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from edr_xarray.errors import EdrCoverageJsonError, EdrUnsupportedFeatureError

__all__ = ["Axis", "CoverageData", "ParameterDef", "parse_coverage"]

_FLOAT_DTYPES = frozenset({"float", "double"})


@dataclass(frozen=True)
class ParameterDef:
    """Metadata for a single parameter (variable)."""

    name: str
    unit: str | None
    standard_name: str | None
    long_name: str | None
    cell_methods: str | None


@dataclass(frozen=True, eq=False)
class Axis:
    """A single domain axis with its coordinate values."""

    name: str
    values: np.ndarray


@dataclass(frozen=True, eq=False)
class CoverageData:
    """Parsed CoverageJSON Coverage with domain axes and data ranges."""

    axes: dict[str, Axis]
    axis_names: tuple[str, ...]
    shape: tuple[int, ...]
    parameters: dict[str, ParameterDef]
    ranges: dict[str, np.ndarray]


def _parse_axis_values(name: str, spec: dict[str, Any]) -> np.ndarray:
    if "values" in spec:
        raw = spec["values"]
        if name == "t":
            stripped = [(s[:-1] if isinstance(s, str) and s.endswith("Z") else s) for s in raw]
            return np.array(
                [np.datetime64(s, "ns") for s in stripped],
                dtype="datetime64[ns]",
            )
        return np.asarray(raw, dtype=np.float64)
    if "start" in spec and "stop" in spec and "num" in spec:
        return np.linspace(
            float(spec["start"]), float(spec["stop"]), int(spec["num"]), dtype=np.float64
        )
    raise EdrCoverageJsonError(f"axis '{name}' must define either 'values' or 'start'/'stop'/'num'")


def _nested_str(spec: dict[str, Any], *path: str) -> str | None:
    cur: Any = spec
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur if isinstance(cur, str) else None


def _parse_parameter(name: str, spec: dict[str, Any]) -> ParameterDef:
    return ParameterDef(
        name=name,
        unit=_nested_str(spec, "unit", "symbol", "value"),
        standard_name=_nested_str(spec, "observedProperty", "id"),
        long_name=_nested_str(spec, "observedProperty", "label", "en"),
        cell_methods=_nested_str(spec, "measurementType", "method"),
    )


def _parse_range(
    name: str,
    spec: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[int, ...], np.ndarray]:
    rtype = spec.get("type")
    if rtype == "TiledNdArray":
        raise EdrUnsupportedFeatureError("TiledNdArray ranges not supported in v1")
    if rtype != "NdArray":
        raise EdrCoverageJsonError(f"range '{name}' has unsupported type '{rtype}'")

    axis_names: tuple[str, ...] = tuple(spec["axisNames"])
    shape: tuple[int, ...] = tuple(spec["shape"])
    values: list[Any] = spec["values"]

    expected = math.prod(shape) if shape else 1
    if len(values) != expected:
        raise EdrCoverageJsonError(
            f"value count {len(values)} does not match shape product {expected}"
        )

    data_type = spec.get("dataType")
    if data_type in _FLOAT_DTYPES:
        cleaned = [np.nan if v is None else float(v) for v in values]
        arr = np.asarray(cleaned, dtype=np.float64).reshape(shape)
    else:
        if any(v is None for v in values):
            raise EdrCoverageJsonError("null values in integer range are not supported")
        arr = np.asarray(values).reshape(shape)

    return axis_names, shape, arr


def parse_coverage(payload: dict[str, Any]) -> CoverageData:
    """Parse a CoverageJSON document into a :class:`CoverageData` dataclass.

    Only Grid domains with NdArray ranges are accepted. Any deviation raises
    either :class:`EdrUnsupportedFeatureError` (known but unsupported feature)
    or :class:`EdrCoverageJsonError` (malformed input).
    """
    domain = payload.get("domain")
    if not isinstance(domain, dict):
        raise EdrCoverageJsonError("payload missing 'domain' object")

    dt = domain.get("domainType")
    if dt != "Grid":
        raise EdrUnsupportedFeatureError(f"only Grid domainType supported in v1, got '{dt}'")

    axes_raw = domain.get("axes")
    if not isinstance(axes_raw, dict):
        raise EdrCoverageJsonError("domain missing 'axes' object")

    axes: dict[str, Axis] = {
        name: Axis(name=name, values=_parse_axis_values(name, spec))
        for name, spec in axes_raw.items()
    }

    parameters_raw = payload.get("parameters")
    if not isinstance(parameters_raw, dict):
        raise EdrCoverageJsonError("payload missing 'parameters' object")
    parameters: dict[str, ParameterDef] = {
        name: _parse_parameter(name, spec) for name, spec in parameters_raw.items()
    }

    ranges_raw = payload.get("ranges")
    if not isinstance(ranges_raw, dict):
        raise EdrCoverageJsonError("payload missing 'ranges' object")
    if not ranges_raw:
        raise EdrCoverageJsonError("payload contains no ranges")

    canonical_axis_names: tuple[str, ...] | None = None
    canonical_shape: tuple[int, ...] | None = None
    ranges: dict[str, np.ndarray] = {}

    for name, spec in ranges_raw.items():
        axis_names, shape, arr = _parse_range(name, spec)
        if canonical_axis_names is None:
            canonical_axis_names = axis_names
            canonical_shape = shape
        else:
            if axis_names != canonical_axis_names:
                raise EdrCoverageJsonError("ranges have inconsistent axisNames")
            if shape != canonical_shape:
                raise EdrCoverageJsonError("ranges have inconsistent shape")
        ranges[name] = arr

    assert canonical_axis_names is not None
    assert canonical_shape is not None

    for i, axis_name in enumerate(canonical_axis_names):
        if axis_name not in axes:
            raise EdrCoverageJsonError(
                f"axis '{axis_name}' referenced by range axisNames not in domain.axes"
            )
        axis_len = len(axes[axis_name].values)
        if axis_len != canonical_shape[i]:
            raise EdrCoverageJsonError(
                f"axis '{axis_name}' length {axis_len} does not match "
                f"shape[{i}]={canonical_shape[i]}"
            )

    return CoverageData(
        axes=axes,
        axis_names=canonical_axis_names,
        shape=canonical_shape,
        parameters=parameters,
        ranges=ranges,
    )
