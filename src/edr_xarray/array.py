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

    def _selection_length(self, axis_index: int, idx: Any) -> int:  # noqa: ANN401
        axis_len = self.shape[axis_index]
        if isinstance(idx, int):
            return 1
        if isinstance(idx, slice):
            return len(range(*idx.indices(axis_len)))
        return axis_len

    def _normalize_axes(
        self,
        cov: CoverageData,
        arr: np.ndarray[Any, Any],
        key: tuple[Any, ...],
    ) -> np.ndarray[Any, Any]:
        expected_axis_names = tuple(axis.name for axis in self._axes)
        returned_axis_names = list(cov.axis_names)
        if arr.ndim != len(returned_axis_names):
            raise EdrCoverageJsonError(
                f"server returned array rank {arr.ndim} for parameter "
                f"'{self._parameter_id}', but axisNames has {len(returned_axis_names)} axes"
            )
        extra_axis_names = sorted(set(returned_axis_names) - set(expected_axis_names))
        if extra_axis_names:
            raise EdrCoverageJsonError(
                f"server returned unexpected axisNames {extra_axis_names} "
                f"for parameter '{self._parameter_id}'; expected axes {expected_axis_names}"
            )

        normalized = arr
        for target_position, axis_name in enumerate(expected_axis_names):
            if axis_name in returned_axis_names:
                current_position = returned_axis_names.index(axis_name)
                if current_position != target_position:
                    normalized = np.moveaxis(normalized, current_position, target_position)
                    returned_axis_names.pop(current_position)
                    returned_axis_names.insert(target_position, axis_name)
            else:
                if self._selection_length(target_position, key[target_position]) != 1:
                    raise EdrCoverageJsonError(
                        f"server omitted axis '{axis_name}' for parameter "
                        f"'{self._parameter_id}', but the requested xarray selection "
                        "requires more than one coordinate on that axis"
                    )
                normalized = np.expand_dims(normalized, axis=target_position)
                returned_axis_names.insert(target_position, axis_name)

        return normalized

    def _validate_prefetch_shape(
        self,
        key: tuple[Any, ...],
        arr: np.ndarray[Any, Any],
    ) -> None:
        if arr.ndim != len(self._axes):
            raise EdrCoverageJsonError(
                f"server returned array rank {arr.ndim} for parameter "
                f"'{self._parameter_id}', but xarray declared {len(self._axes)} dimensions"
            )
        for axis_index, idx in enumerate(key):
            axis = self._axes[axis_index]
            if isinstance(idx, int) and arr.shape[axis_index] == 0:
                raise EdrCoverageJsonError(
                    f"server returned no coordinates on axis '{axis.name}' for scalar "
                    f"xarray indexer {idx!r}; expected 1"
                )
            if isinstance(idx, int) and arr.shape[axis_index] not in {1, self.shape[axis_index]}:
                raise EdrCoverageJsonError(
                    f"server returned {arr.shape[axis_index]} coordinates on axis "
                    f"'{axis.name}' for scalar xarray indexer {idx!r}; expected either "
                    f"1 or the full declared axis length {self.shape[axis_index]}"
                )

    def _validate_result_shape(
        self,
        result_shape: tuple[int, ...],
        arr: np.ndarray[Any, Any],
    ) -> None:
        if arr.shape != result_shape:
            raise EdrCoverageJsonError(
                f"server returned shape {arr.shape} for parameter '{self._parameter_id}', "
                f"but xarray expected shape {result_shape} from declared shape {self.shape}"
            )

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
            arr = self._normalize_axes(cov, arr, key)

        self._validate_prefetch_shape(key, arr)

        arr = np.asarray(arr[self._post_fetch_selector(key, arr)])
        self._validate_result_shape(result_shape, arr)

        return cast("np.ndarray[Any, np.dtype[Any]]", arr)

    def __getstate__(self) -> dict[str, Any]:
        """Return pickleable state. The store back-ref is preserved."""
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state from pickle."""
        for slot, value in state.items():
            object.__setattr__(self, slot, value)
