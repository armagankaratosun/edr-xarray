"""EdrBackendArray — lazy xarray BackendArray backed by an EDR /cube endpoint.

All cube fetches route through the EdrDataStore's hook methods:
  - _translate_indexer: converts xarray indexer key to EDR query params
  - _request: makes the HTTP request (subclass-overridable for auth)
  - _parse_coveragejson: parses the CoverageJSON response

This routing ensures subclasses that override any hook see ALL cube traffic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from xarray.backends import BackendArray
from xarray.core import indexing

from edr_xarray.errors import EdrCoverageJsonError

if TYPE_CHECKING:
    from typing import Protocol

    import httpx

    from edr_xarray.coveragejson import CoverageData
    from edr_xarray.indexer import AxisInfo

    class EdrDataStore(Protocol):
        """Store hook protocol needed by EdrBackendArray."""

        def _translate_indexer(
            self, key: tuple[Any, ...], axes: tuple[AxisInfo, ...]
        ) -> Mapping[str, str]: ...

        def _request(
            self, method: str, url: str, *, params: Mapping[str, str]
        ) -> httpx.Response: ...

        def _parse_coveragejson(self, payload: dict[str, Any]) -> CoverageData: ...


__all__ = ["EdrBackendArray"]


class EdrBackendArray(BackendArray):
    """Lazy xarray backend array that fetches data from an EDR /cube endpoint.

    Data is fetched on demand via _raw_indexing_method. All HTTP calls flow
    through the parent EdrDataStore's hook methods, preserving subclass extensibility.

    Note: the _store back-reference is preserved during pickling. The store's
    __getstate__ drops its unpickleable HTTP session, so this array stays
    functional after unpickling (with a fresh session).
    """

    __slots__ = (
        "_axes",
        "_cube_url",
        "_dtype",
        "_extra_query_params",
        "_parameter_id",
        "_shape",
        "_store",
    )

    def __init__(
        self,
        *,
        store: EdrDataStore,
        cube_url: str,
        parameter_id: str,
        axes: tuple[AxisInfo, ...],
        shape: tuple[int, ...],
        dtype: np.dtype[Any],
        extra_query_params: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize a lazy array without fetching any data."""
        self._store = store
        self._cube_url = cube_url
        self._parameter_id = parameter_id
        self._axes = axes
        self._shape = shape
        self._dtype = dtype
        self._extra_query_params = dict(extra_query_params) if extra_query_params else {}

    @property
    def shape(self) -> tuple[int, ...]:
        """Array shape in xarray's declared dimension order."""
        return self._shape

    @property
    def dtype(self) -> np.dtype[Any]:
        """Array NumPy dtype."""
        return self._dtype

    def __getitem__(self, key: indexing.ExplicitIndexer) -> np.ndarray[Any, np.dtype[Any]]:
        """Fetch the requested data through xarray's explicit indexing adapter."""
        return cast(
            "np.ndarray[Any, np.dtype[Any]]",
            indexing.explicit_indexing_adapter(
                key,
                self.shape,
                indexing.IndexingSupport.BASIC,
                self._raw_indexing_method,
            ),
        )

    def _result_shape(self, key: tuple[Any, ...]) -> tuple[int, ...]:
        shape = []
        for idx, axis_len in zip(key, self.shape, strict=True):
            if isinstance(idx, int):
                continue
            if isinstance(idx, slice):
                shape.append(len(range(*idx.indices(axis_len))))
            else:
                shape.append(axis_len)
        return tuple(shape)

    def _post_fetch_selector(
        self, key: tuple[Any, ...], arr: np.ndarray[Any, Any]
    ) -> tuple[Any, ...]:
        selector: list[Any] = []
        for i, idx in enumerate(key):
            if isinstance(idx, int):
                selector.append(0 if arr.shape[i] != self.shape[i] else idx)
            elif isinstance(idx, slice):
                if arr.shape[i] == self.shape[i]:
                    selector.append(idx)
                elif idx.step is not None and idx.step != 1:
                    selector.append(slice(0, None, idx.step))
                else:
                    selector.append(slice(None))
            else:
                selector.append(slice(None))
        return tuple(selector)

    def _raw_indexing_method(self, key: tuple[Any, ...]) -> np.ndarray[Any, np.dtype[Any]]:
        result_shape = self._result_shape(key)
        if any(axis_len == 0 for axis_len in result_shape):
            return np.empty(result_shape, dtype=self.dtype)

        # Open-time defaults (bbox/datetime fallbacks, format, crs, z) go first.
        # Indexer-supplied selectors (from .isel/.sel) override them when narrower.
        query_params: dict[str, str] = dict(self._extra_query_params)
        query_params.update(self._store._translate_indexer(key, self._axes))
        query_params["parameter-name"] = self._parameter_id
        query_params.setdefault("f", "CoverageJSON")

        response = self._store._request("GET", self._cube_url, params=query_params)

        try:
            payload = response.json()
        except Exception as exc:
            raise EdrCoverageJsonError(
                f"could not parse CoverageJSON response for parameter '{self._parameter_id}'"
            ) from exc

        cov = self._store._parse_coveragejson(payload)

        try:
            arr = cov.ranges[self._parameter_id]
        except KeyError as exc:
            raise EdrCoverageJsonError(
                f"server returned no range for parameter '{self._parameter_id}'"
            ) from exc

        expected_axis_names = tuple(a.name for a in self._axes)
        if cov.axis_names != expected_axis_names:
            permutation = [list(cov.axis_names).index(n) for n in expected_axis_names]
            arr = np.transpose(arr, axes=permutation)

        arr = arr[self._post_fetch_selector(key, arr)]

        return cast("np.ndarray[Any, np.dtype[Any]]", arr)

    def __getstate__(self) -> dict[str, Any]:
        """Return pickleable state. The store back-ref is preserved."""
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state from pickle."""
        for slot, value in state.items():
            object.__setattr__(self, slot, value)
