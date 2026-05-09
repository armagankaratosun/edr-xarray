"""httpx.Client wrapper with error mapping and session ownership tracking.

Provides:
  - Transport.request() — low-level HTTP, returns httpx.Response; raises EdrServerError on failure
  - Transport.get_json() — convenience wrapper returning parsed dict
  - Pickle safety via __getstate__/__setstate__ (drops the session, creates new on restore)
  - Session ownership: owned sessions closed on Transport.close(); injected sessions left open
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from edr_xarray.errors import EdrServerError

__all__ = ["Transport"]


class Transport:
    """Thin httpx.Client wrapper for edr-xarray HTTP requests."""

    def __init__(
        self,
        *,
        session: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Create a Transport.

        If session is provided, it is used as-is and will NOT be closed by this object.
        If session is None, a new httpx.Client is created and owned by this object.

        Args:
            session: Optional pre-configured httpx.Client (e.g. with auth headers).
            timeout: Default request timeout in seconds (only used for owned sessions).

        """
        if session is not None:
            self._session: httpx.Client = session
            self._owns: bool = False
        else:
            self._session = httpx.Client(timeout=timeout)
            self._owns = True

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Make an HTTP request and return the raw Response.

        Raises:
            EdrServerError: On network failures or non-2xx status codes.

        """
        try:
            response = self._session.request(method, url, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise EdrServerError(
                f"network error fetching {url}: {exc}",
                url=url,
            ) from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _extract_problem_detail(response) or response.text or "non-2xx response"
            raise EdrServerError(
                detail,
                status_code=response.status_code,
                url=str(response.request.url),
            ) from exc

        return response

    def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """GET url and return parsed JSON body.

        Raises:
            EdrServerError: On HTTP failures or non-JSON response.

        """
        response = self.request("GET", url, params=params, headers=headers)
        try:
            return response.json()  # type: ignore[no-any-return]
        except Exception as exc:
            raise EdrServerError("non-JSON response", url=url) from exc

    def close(self) -> None:
        """Close the underlying session if this Transport owns it. Idempotent."""
        if self._owns and not self._session.is_closed:
            self._session.close()

    def __enter__(self) -> Transport:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close the owned session (if any) on context exit."""
        self.close()

    def __getstate__(self) -> dict[str, Any]:
        """Drop the session for pickle safety (httpx.Client is not pickleable)."""
        state = self.__dict__.copy()
        state["_session"] = None
        state["_owns"] = False
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state and create a fresh owned session on unpickle."""
        self.__dict__.update(state)
        self._session = httpx.Client()
        self._owns = True


def _extract_problem_detail(response: httpx.Response) -> str | None:
    """Extract the 'detail' field from an RFC 7807 problem+json response body."""
    content_type = response.headers.get("content-type", "")
    if "problem+json" not in content_type and "problem" not in content_type:
        return None
    try:
        body = json.loads(response.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    return str(detail) if detail is not None else None
