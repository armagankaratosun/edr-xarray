"""EdrBackendEntrypoint — registers the 'edr' xarray backend engine.

Usage:
    import xarray as xr
    ds = xr.open_dataset(
        "https://edr.example.com/collections/temperature_2m",
        engine="edr",
        parameter_names=["t2m"],
        bbox=(-3.5, 50.2, -2.1, 51.0),
        datetime="2023-01-01T00:00:00Z/2023-01-07T00:00:00Z",
    )
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

import httpx
import xarray as xr
from xarray.backends import BackendEntrypoint

from edr_xarray.store import EdrDataStore

__all__ = ["EdrBackendEntrypoint"]


class EdrBackendEntrypoint(BackendEntrypoint):
    """xarray backend for OGC API - Environmental Data Retrieval (EDR) /cubes endpoint.

    Opens any EDR 1.1-compliant collection as a lazy xarray Dataset.

    Supports:
    - /cubes endpoint with CoverageJSON response
    - 2D, 3D, and 4D cubes (lat/lon/[z]/time)
    - Lazy fetch via BackendArray (data only loaded on .values/.load()/.compute())
    - Dask integration via preferred_chunks
    - Pickle-safe for Dask multiprocessing
    - Subclassable via EdrDataStore hook methods
    """

    description: ClassVar[str] = (
        "Lazy xarray backend for OGC API - Environmental Data Retrieval (EDR) /cubes endpoint"
    )
    url: ClassVar[str] = "https://github.com/edr-xarray/edr-xarray"
    open_dataset_parameters: ClassVar[tuple[str, ...] | None] = (
        "filename_or_obj",
        "drop_variables",
        "instance",
        "parameter_names",
        "bbox",
        "datetime",
        "crs",
        "z",
        "session",
        "discovery",
        "timeout",
    )

    def open_dataset(
        self,
        filename_or_obj: object,
        *,
        drop_variables: str | Iterable[str] | None = None,
        # Standard xarray decoders (accepted but EDR handles these internally)
        mask_and_scale: bool = True,
        decode_times: bool = True,
        decode_coords: bool | str = True,
        use_cftime: bool | None = None,
        decode_timedelta: bool | None = None,
        concat_characters: bool = True,
        # EDR-specific kwargs
        instance: str | None = None,
        parameter_names: list[str] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        datetime: str | None = None,
        crs: str | None = None,
        z: float | str | None = None,
        session: object = None,
        discovery: str = "probe",
        timeout: float = 30.0,
    ) -> xr.Dataset:
        """Open an EDR collection as a lazy xarray Dataset.

        Args:
            filename_or_obj: URL of the EDR collection resource.
                Must be a string containing '/collections/', e.g.:
                'https://edr.example.com/collections/temperature_2m'
            drop_variables: Variable name(s) to exclude from the dataset.
            mask_and_scale: Accepted for xarray compatibility.
            decode_times: Accepted for xarray compatibility.
            decode_coords: Accepted for xarray compatibility.
            use_cftime: Accepted for xarray compatibility.
            decode_timedelta: Accepted for xarray compatibility.
            concat_characters: Accepted for xarray compatibility.
            instance: Optional instance ID for collections with instances
                (e.g. forecast runs). Fetches instance metadata and reads data from
                /collections/{id}/instances/{instance}/cube.
            parameter_names: List of parameter names to include. If None,
                all advertised parameters are included.
            bbox: Spatial subset as (lon_min, lat_min, lon_max, lat_max) in CRS84.
                Applied as a static filter to all fetches.
            datetime: Temporal subset as ISO 8601 instant or 'start/end' interval.
            crs: Output CRS identifier (must be in collection's advertised list).
            z: Vertical level as scalar or 'lo/hi' range string.
            session: Pre-configured httpx.Client for authentication/custom headers.
            discovery: Axis discovery mode: 'probe' (default), 'metadata_only', 'strict'.
            timeout: HTTP request timeout in seconds (for owned sessions only).

        """
        del (
            mask_and_scale,
            decode_times,
            decode_coords,
            use_cftime,
            decode_timedelta,
            concat_characters,
        )
        if not isinstance(filename_or_obj, str):
            raise ValueError(
                f"EDR backend requires a string URL, got {type(filename_or_obj).__name__}"
            )
        if "/collections/" not in filename_or_obj:
            raise ValueError(
                "EDR backend requires a string URL pointing to a /collections/{id} resource; "
                f"got: {filename_or_obj!r}"
            )

        if session is None:
            actual_session = None
        elif isinstance(session, httpx.Client):
            actual_session = session
        else:
            raise TypeError(
                f"session must be an httpx.Client or None, got {type(session).__name__}"
            )

        store = EdrDataStore(
            collection_url=filename_or_obj,
            instance=instance,
            parameter_names=parameter_names,
            bbox=bbox,
            datetime=datetime,
            crs=crs,
            z=z,
            session=actual_session,
            discovery=discovery,
            timeout=timeout,
        )
        ds = store.build_dataset()

        if drop_variables:
            if isinstance(drop_variables, str):
                drop_variables = [drop_variables]
            ds = ds.drop_vars(list(drop_variables))
            ds.set_close(store.close)

        return ds

    def guess_can_open(self, filename_or_obj: object) -> bool:
        """Return True if this appears to be an EDR collection URL."""
        if not isinstance(filename_or_obj, str):
            return False
        url = filename_or_obj.lower()
        if "/collections/" not in url:
            return False
        return not ("/items" in url or "/wmts" in url)
