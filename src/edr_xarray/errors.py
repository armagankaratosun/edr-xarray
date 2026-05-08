"""Custom exceptions for edr-xarray."""

from __future__ import annotations


class EdrXarrayError(Exception):
    """Base class for all edr-xarray errors."""


class EdrServerError(EdrXarrayError):
    """HTTP-level failure: network error, 4xx, or 5xx response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
    ) -> None:
        """Store status_code and url for later inspection."""
        self.status_code = status_code
        self.url = url
        super().__init__(message)

    def __str__(self) -> str:
        """Include status_code and url in the string representation."""
        base = super().__str__()
        parts = [base]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.url is not None:
            parts.append(f"url={self.url}")
        if len(parts) == 1:
            return base
        return f"{base} [{', '.join(parts[1:])}]"


class EdrMetadataError(EdrXarrayError):
    """Collection metadata is missing required fields or malformed."""


class EdrCoverageJsonError(EdrXarrayError):
    """CoverageJSON response is malformed or unparseable."""


class EdrUnsupportedFeatureError(EdrXarrayError):
    """Requested feature is not supported in v1."""


class EdrConformanceError(EdrXarrayError):
    """Server does not claim required conformance class."""
