"""Version metadata alignment tests."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import edr_xarray


def test_version_metadata_matches_version_file() -> None:
    """The package version is sourced from the root VERSION file."""
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    expected = version_file.read_text(encoding="utf-8").strip()

    assert version("edr-xarray") == expected
    assert edr_xarray.__version__ == expected
