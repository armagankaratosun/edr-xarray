"""Shared pytest fixtures for edr-xarray tests.

NO edr_xarray module imports here — fixtures are pure inputs.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_httpserver import HTTPServer

_DATA_DIR = Path(__file__).parent / "data"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((_DATA_DIR / name).read_text())


@pytest.fixture()
def sample_cov_grid_3d() -> dict[str, Any]:
    """3D Grid CoverageJSON (t=1, y=2, x=2) with temperature parameter."""
    return _load_fixture("cov_grid_3d.json")


@pytest.fixture()
def sample_cov_grid_4d() -> dict[str, Any]:
    """4D Grid CoverageJSON (t=1, z=3, y=2, x=2) with temperature parameter."""
    return _load_fixture("cov_grid_4d.json")


@pytest.fixture()
def sample_cov_grid_with_nulls() -> dict[str, Any]:
    """3D Grid CoverageJSON with one null value in the temperature range."""
    return _load_fixture("cov_grid_with_nulls.json")


@pytest.fixture()
def sample_collection_metadata(httpserver: HTTPServer) -> dict[str, Any]:
    """Minimal valid EDR collection metadata.

    The cube link href is set to the httpserver URL so the mock can serve it.
    """
    payload = copy.deepcopy(_load_fixture("collection_metadata_basic.json"))
    cube_href = httpserver.url_for("/collections/test_collection/cube")
    payload["data_queries"]["cube"]["link"]["href"] = cube_href
    return payload


@pytest.fixture()
def sample_metadata_with_instances(httpserver: HTTPServer) -> dict[str, Any]:
    """Return collection metadata that advertises an instances link."""
    payload = copy.deepcopy(_load_fixture("collection_metadata_with_instances.json"))
    cube_href = httpserver.url_for("/collections/test_collection/instances/i001/cube")
    payload["data_queries"]["cube"]["link"]["href"] = cube_href
    instances_href = httpserver.url_for("/collections/test_collection/instances")
    payload["data_queries"]["instances"]["link"]["href"] = instances_href
    return payload


def register_metadata_endpoint(
    httpserver: HTTPServer, collection_id: str, payload: dict[str, Any]
) -> None:
    """Register a GET /collections/{collection_id} endpoint returning payload."""
    httpserver.expect_request(
        f"/collections/{collection_id}", method="GET"
    ).respond_with_json(payload)


def register_cube_endpoint(
    httpserver: HTTPServer,
    collection_id: str,
    payload: dict[str, Any],
    *,
    status: int = 200,
) -> None:
    """Register a GET cube endpoint returning CoverageJSON or error."""
    if status == 200:
        httpserver.expect_ordered_request(
            f"/collections/{collection_id}/cube", method="GET"
        ).respond_with_json(payload)
    else:
        httpserver.expect_ordered_request(
            f"/collections/{collection_id}/cube", method="GET"
        ).respond_with_data(
            json.dumps({"type": "about:blank", "status": status, "detail": "error"}),
            status=status,
            content_type="application/problem+json",
        )


def request_log(httpserver: HTTPServer) -> list[str]:
    """Return list of request paths+queries seen by the httpserver."""
    log = []
    for request, _ in httpserver.log:
        url = request.full_path if request.query_string else request.path
        log.append(url)
    return log
