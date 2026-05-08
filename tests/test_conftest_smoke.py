"""Smoke test: verify pytest-httpserver is functional."""
from __future__ import annotations

import httpx
from pytest_httpserver import HTTPServer


def test_httpserver_serves_json(httpserver: HTTPServer) -> None:
    """pytest-httpserver can register and serve a JSON response."""
    httpserver.expect_request("/test", method="GET").respond_with_json({"ok": True})
    url = httpserver.url_for("/test")
    response = httpx.get(url)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_httpserver_url_for_returns_absolute_url(httpserver: HTTPServer) -> None:
    """url_for returns a full http://host:port/path URL."""
    url = httpserver.url_for("/my/path")
    assert url.startswith("http://")
    assert "/my/path" in url
