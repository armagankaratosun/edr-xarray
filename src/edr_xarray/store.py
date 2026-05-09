"""EdrDataStore — orchestrator for EDR collection open/build.

Not an xarray AbstractDataStore subclass — this is our own orchestrator.
All external access goes through documented subclass hooks that downstream
server-specific packages can override to add custom behavior.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, cast

import httpx
import numpy as np
import xarray as xr

from edr_xarray.array import EdrBackendArray
from edr_xarray.builder import (
    build_coord_variables,
    build_data_variables,
    build_global_attrs,
)
from edr_xarray.coveragejson import CoverageData, parse_coverage
from edr_xarray.discovery import DiscoveryMode, discover_axes, validate_discovery_mode
from edr_xarray.errors import EdrMetadataError
from edr_xarray.indexer import AxisInfo, translate_indexer
from edr_xarray.metadata import (
    CollectionMetadata,
    cube_url,
    parse_collection_metadata,
)
from edr_xarray.query import (
    encode_bbox,
    encode_crs,
    encode_datetime,
    encode_z,
    negotiate_format,
)
from edr_xarray.transport import Transport

__all__ = ["EdrDataStore"]


class EdrDataStore:
    """Orchestrate EDR collection metadata, axis discovery, and lazy Dataset build."""

    def __init__(
        self,
        *,
        collection_url: str,
        instance: str | None = None,
        parameter_names: list[str] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        datetime: str | None = None,
        crs: str | None = None,
        z: float | str | None = None,
        session: httpx.Client | None = None,
        discovery: str = "probe",
        timeout: float = 30.0,
    ) -> None:
        """Initialize store configuration without making network requests."""
        self.collection_url = collection_url
        self.instance = instance
        self.parameter_names = parameter_names
        self.bbox = bbox
        self.datetime = datetime
        self.crs = crs
        self.z = z
        self.discovery: DiscoveryMode = validate_discovery_mode(discovery)
        self.timeout = timeout
        self._transport = Transport(session=session, timeout=timeout)
        self._metadata: CollectionMetadata | None = None
        self._cube_url: str | None = None

    def build_dataset(self) -> xr.Dataset:
        """Fetch collection metadata and build a lazy Dataset."""
        response = self._request("GET", self.collection_url)
        try:
            metadata_payload = response.json()
        except Exception as exc:
            raise EdrMetadataError("collection metadata is not valid JSON") from exc
        if not isinstance(metadata_payload, dict):
            raise EdrMetadataError("collection metadata JSON must be an object")

        self._metadata = self._parse_collection_metadata(cast("dict[str, Any]", metadata_payload))
        selected_format = self._negotiate_output_format(self._metadata.cube_link.output_formats)
        self._cube_url = self._build_cube_url(self.collection_url, self.instance)
        validated_crs = encode_crs(
            self.crs,
            self._metadata.cube_link.crs_options or self._metadata.crs_options,
        )
        axes = self._discover_axes(self._metadata)

        extra: dict[str, str] = {"f": selected_format}
        if validated_crs is not None:
            extra["crs"] = validated_crs
        if self.z is not None:
            z_str = encode_z(self.z)
            if z_str is not None:
                extra["z"] = z_str
        # Always send bbox and datetime so servers that require them don't reject
        # unsubsetted fetches.  User-supplied values take priority; the collection
        # extent is the fallback.
        if self.datetime is not None:
            dt_str = encode_datetime(self.datetime)
            if dt_str is not None:
                extra["datetime"] = dt_str
        elif self._metadata.temporal is not None:
            t = self._metadata.temporal
            lo, hi = t.interval
            extra["datetime"] = lo if lo == hi else f"{lo}/{hi}"
        if self.bbox is not None:
            extra["bbox"] = encode_bbox(self.bbox)
        else:
            extra["bbox"] = encode_bbox(self._metadata.spatial.bbox)

        cube_url_str = self._cube_url
        store_ref = self

        def make_array(parameter_id: str, shape: tuple[int, ...]) -> EdrBackendArray:
            return EdrBackendArray(
                store=store_ref,
                cube_url=cube_url_str,
                parameter_id=parameter_id,
                axes=axes,
                shape=shape,
                dtype=np.dtype("float64"),
                extra_query_params=extra,
            )

        if self.parameter_names is not None:
            unknown = set(self.parameter_names) - set(self._metadata.parameters)
            if unknown:
                raise EdrMetadataError(
                    f"parameter(s) {sorted(unknown)} not found in collection; "
                    f"available: {sorted(self._metadata.parameters)}"
                )
            filtered_params = {
                k: v for k, v in self._metadata.parameters.items() if k in self.parameter_names
            }
            filtered_metadata = dataclasses.replace(self._metadata, parameters=filtered_params)
        else:
            filtered_metadata = self._metadata

        data_vars = build_data_variables(filtered_metadata, axes, make_array)
        coord_vars = build_coord_variables(axes, self._metadata)
        global_attrs = build_global_attrs(self._metadata)

        ds = xr.Dataset(
            data_vars,
            coords=xr.Coordinates(coord_vars, indexes={}),
            attrs=global_attrs,
        )
        ds.set_close(self.close)
        return ds

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Low-level HTTP request hook. Override for custom auth, signing, retry."""
        return self._transport.request(method, url, params=params, headers=headers)

    def _parse_collection_metadata(self, payload: dict[str, Any]) -> CollectionMetadata:
        """Parse raw metadata JSON. Override to handle server-specific extensions."""
        return parse_collection_metadata(payload)

    def _negotiate_output_format(self, advertised: tuple[str, ...]) -> str:
        """Select output format. Override to prefer alternatives (e.g. NetCDF)."""
        return negotiate_format(advertised)

    def _build_cube_url(self, collection_url: str, instance: str | None) -> str:
        """Build the cube endpoint URL. Override for non-standard routing."""
        assert self._metadata is not None, "_build_cube_url called before metadata was fetched"
        return cube_url(self._metadata, instance, base_url=collection_url)

    def _parse_coveragejson(self, payload: dict[str, Any]) -> CoverageData:
        """Parse CoverageJSON response. Override for server-specific extensions."""
        return parse_coverage(payload)

    def _translate_indexer(
        self, key: tuple[Any, ...], axes: tuple[AxisInfo, ...]
    ) -> dict[str, str]:
        """Translate xarray indexer to EDR query params. Override for custom slicing."""
        return translate_indexer(key, axes)

    def _discover_axes(self, metadata: CollectionMetadata) -> tuple[AxisInfo, ...]:
        """Discover domain axes. Override for server-specific axis discovery."""
        assert self._cube_url is not None, "_discover_axes called before _cube_url was set"
        return discover_axes(
            metadata,
            mode=self.discovery,
            request_callable=self._request,
            parse_coverage_callable=self._parse_coveragejson,
            cube_url=self._cube_url,
            instance=self.instance,
            user_bbox=self.bbox,
        )

    def close(self) -> None:
        """Close the underlying transport (only if owned). Idempotent."""
        self._transport.close()

    def __getstate__(self) -> dict[str, Any]:
        """Drop transport for pickle safety; preserve all other state."""
        state = self.__dict__.copy()
        del state["_transport"]
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state; create a fresh transport."""
        self.__dict__.update(state)
        self._transport = Transport(timeout=state.get("timeout", 30.0))
