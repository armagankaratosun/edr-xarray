"""edr-xarray: Generic OGC API-EDR 1.1 xarray backend."""
# pyright: reportMissingImports=false
from __future__ import annotations

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

__version__ = "0.1.0"
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
