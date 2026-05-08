"""Tests for edr_xarray.errors — exception hierarchy."""

# pyright: reportMissingImports=false
from __future__ import annotations

import pytest

from edr_xarray.errors import (
    EdrConformanceError,
    EdrCoverageJsonError,
    EdrMetadataError,
    EdrServerError,
    EdrUnsupportedFeatureError,
    EdrXarrayError,
)


def test_base_class_is_exception() -> None:
    """EdrXarrayError is a plain Exception subclass."""
    assert issubclass(EdrXarrayError, Exception)


def test_all_subclasses_inherit_base() -> None:
    """All package errors inherit from EdrXarrayError."""
    for cls in (
        EdrServerError,
        EdrMetadataError,
        EdrCoverageJsonError,
        EdrUnsupportedFeatureError,
        EdrConformanceError,
    ):
        assert issubclass(cls, EdrXarrayError), f"{cls} not a subclass of EdrXarrayError"


def test_edr_server_error_stores_status_code_and_url() -> None:
    """EdrServerError exposes status_code and url attributes."""
    err = EdrServerError("not found", status_code=404, url="http://srv/cube")
    assert err.status_code == 404
    assert err.url == "http://srv/cube"


def test_edr_server_error_optional_kwargs() -> None:
    """EdrServerError works with no optional kwargs."""
    err = EdrServerError("boom")
    assert err.status_code is None
    assert err.url is None


def test_edr_server_error_str_includes_status_and_url() -> None:
    """str(EdrServerError) includes status_code, url, and message."""
    err = EdrServerError("not found", status_code=404, url="http://srv/cube")
    s = str(err)
    assert "404" in s
    assert "http://srv/cube" in s
    assert "not found" in s


def test_raise_from_preserves_cause() -> None:
    """Raise ... from exc preserves __cause__ on EdrServerError."""
    inner = ConnectionError("upstream down")
    outer = EdrServerError("cube fetch failed", url="http://srv")
    try:
        try:
            raise inner
        except ConnectionError as exc:
            raise outer from exc
    except EdrServerError as e2:
        assert isinstance(e2.__cause__, ConnectionError)
        assert str(e2.__cause__) == "upstream down"


def test_exceptions_are_catchable_as_base() -> None:
    """All subclasses can be caught via EdrXarrayError."""
    for cls in (
        EdrServerError,
        EdrMetadataError,
        EdrCoverageJsonError,
        EdrUnsupportedFeatureError,
        EdrConformanceError,
    ):
        with pytest.raises(EdrXarrayError):
            raise cls("test")
