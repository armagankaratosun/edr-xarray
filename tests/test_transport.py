"""Tests for edr_xarray.transport — httpx.Client wrapper."""

from __future__ import annotations

import pickle

import httpx
import pytest
from pytest_httpserver import HTTPServer

from edr_xarray.errors import EdrServerError
from edr_xarray.transport import Transport


def test_owned_session_is_closed_on_close() -> None:
    """Transport that owns its session closes it on .close()."""
    t = Transport()
    assert t._owns is True
    assert not t._session.is_closed
    t.close()
    assert t._session.is_closed


def test_close_is_idempotent() -> None:
    """Calling close() multiple times does not raise."""
    t = Transport()
    t.close()
    t.close()
    assert t._session.is_closed


def test_context_manager_closes_session() -> None:
    """Using Transport as a context manager closes the owned session on exit."""
    with Transport() as t:
        session = t._session
        assert not session.is_closed
    assert session.is_closed


def test_injected_session_not_closed() -> None:
    """Transport does not close a session that was injected by the caller."""
    external = httpx.Client()
    try:
        t = Transport(session=external)
        assert t._owns is False
        t.close()
        assert not external.is_closed
    finally:
        external.close()


def test_request_returns_response_on_200(httpserver: HTTPServer) -> None:
    """Transport.request returns the raw httpx.Response on a 2xx response."""
    httpserver.expect_request("/ok", method="GET").respond_with_data("hello")
    url = httpserver.url_for("/ok")
    with Transport() as t:
        response = t.request("GET", url)
    assert isinstance(response, httpx.Response)
    assert response.status_code == 200
    assert response.text == "hello"


def test_get_json_returns_parsed_dict(httpserver: HTTPServer) -> None:
    """Transport.get_json returns the parsed JSON body as a dict."""
    httpserver.expect_request("/json", method="GET").respond_with_json({"key": "val"})
    url = httpserver.url_for("/json")
    with Transport() as t:
        body = t.get_json(url)
    assert body == {"key": "val"}


def test_404_raises_edr_server_error(httpserver: HTTPServer) -> None:
    """A 404 response is mapped to EdrServerError with status_code and url."""
    httpserver.expect_request("/missing", method="GET").respond_with_data("not here", status=404)
    url = httpserver.url_for("/missing")
    with Transport() as t, pytest.raises(EdrServerError) as exc_info:
        t.request("GET", url)
    err = exc_info.value
    assert err.status_code == 404
    assert err.url is not None and "/missing" in err.url


def test_500_with_problem_details_extracts_detail(httpserver: HTTPServer) -> None:
    """RFC 7807 problem+json bodies have their 'detail' surfaced in the message."""
    httpserver.expect_request("/boom", method="GET").respond_with_data(
        '{"type": "about:blank", "status": 500, "detail": "internal error"}',
        status=500,
        content_type="application/problem+json",
    )
    url = httpserver.url_for("/boom")
    with Transport() as t, pytest.raises(EdrServerError) as exc_info:
        t.request("GET", url)
    err = exc_info.value
    assert err.status_code == 500
    assert "internal error" in str(err)


def test_get_json_non_json_response_raises(httpserver: HTTPServer) -> None:
    """A successful response with a non-JSON body raises EdrServerError."""
    httpserver.expect_request("/text", method="GET").respond_with_data(
        "not json", content_type="text/plain"
    )
    url = httpserver.url_for("/text")
    with Transport() as t, pytest.raises(EdrServerError) as exc_info:
        t.get_json(url)
    assert "non-JSON" in str(exc_info.value)


def test_pickle_round_trip() -> None:
    """Transport can be pickled and unpickled; the new instance has a fresh session."""
    t = Transport()
    try:
        blob = pickle.dumps(t)
    finally:
        t.close()
    t2 = pickle.loads(blob)
    try:
        assert t2._session is not t._session
        assert t2._owns is True
        assert not t2._session.is_closed
    finally:
        t2.close()


def test_headers_passed_through(httpserver: HTTPServer) -> None:
    """Headers passed to .request are forwarded on the underlying httpx call."""
    httpserver.expect_request(
        "/auth",
        method="GET",
        headers={"Authorization": "Bearer TOKEN"},
    ).respond_with_data("ok")
    url = httpserver.url_for("/auth")
    with Transport() as t:
        response = t.request("GET", url, headers={"Authorization": "Bearer TOKEN"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_network_error_raises_edr_server_error() -> None:
    """A connection failure (e.g. unreachable host) maps to EdrServerError."""
    # Use a port that is virtually guaranteed to refuse connections
    url = "http://127.0.0.1:1/never"
    with Transport(timeout=1.0) as t, pytest.raises(EdrServerError) as exc_info:
        t.request("GET", url)
    err = exc_info.value
    assert err.status_code is None
    assert err.url == url
    assert "network error" in str(err).lower()


def test_query_params_passed_through(httpserver: HTTPServer) -> None:
    """params={...} is encoded into the query string of the outgoing request."""
    httpserver.expect_request(
        "/search",
        method="GET",
        query_string={"q": "rain", "limit": "5"},
    ).respond_with_json({"hits": []})
    url = httpserver.url_for("/search")
    with Transport() as t:
        body = t.get_json(url, params={"q": "rain", "limit": "5"})
    assert body == {"hits": []}


def test_problem_json_with_invalid_body_falls_back(httpserver: HTTPServer) -> None:
    """A problem+json response with an unparseable body falls back to response.text."""
    httpserver.expect_request("/bad", method="GET").respond_with_data(
        "not json at all",
        status=500,
        content_type="application/problem+json",
    )
    url = httpserver.url_for("/bad")
    with Transport() as t, pytest.raises(EdrServerError) as exc_info:
        t.request("GET", url)
    err = exc_info.value
    assert err.status_code == 500
    assert "not json at all" in str(err)


def test_problem_json_with_array_body_falls_back(httpserver: HTTPServer) -> None:
    """A problem+json response whose body is a JSON array (not object) falls back."""
    httpserver.expect_request("/arr", method="GET").respond_with_data(
        "[1, 2, 3]",
        status=500,
        content_type="application/problem+json",
    )
    url = httpserver.url_for("/arr")
    with Transport() as t, pytest.raises(EdrServerError) as exc_info:
        t.request("GET", url)
    err = exc_info.value
    assert err.status_code == 500
    assert "[1, 2, 3]" in str(err)
