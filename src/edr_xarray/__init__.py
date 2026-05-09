"""edr-xarray: Generic OGC API-EDR 1.1 xarray backend."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .array import EdrBackendArray
from .backend import EdrBackendEntrypoint
from .errors import (
    EdrConformanceError,
    EdrCoverageJsonError,
    EdrMetadataError,
    EdrServerError,
    EdrUnsupportedFeatureError,
    EdrXarrayError,
)
from .store import EdrDataStore


def _read_version() -> str:
    try:
        return version("edr-xarray")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[2] / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "0.0.0+unknown"


__version__ = _read_version()
__all__ = [
    "EdrBackendArray",
    "EdrBackendEntrypoint",
    "EdrConformanceError",
    "EdrCoverageJsonError",
    "EdrDataStore",
    "EdrMetadataError",
    "EdrServerError",
    "EdrUnsupportedFeatureError",
    "EdrXarrayError",
    "__version__",
]
