"""Tests for edr_xarray.metadata — pure parser for OGC EDR collection metadata."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from edr_xarray.errors import EdrMetadataError
from edr_xarray.metadata import (
    CollectionMetadata,
    CubeLink,
    ParameterDefinition,
    SpatialExtent,
    TemporalExtent,
    VerticalExtent,
    cube_url,
    parse_collection_metadata,
)


def _minimal_payload() -> dict[str, Any]:
    """Smallest valid payload: id + spatial.bbox + parameter_names + cube href."""
    return {
        "id": "test",
        "extent": {"spatial": {"bbox": [[0.0, 0.0, 1.0, 1.0]]}},
        "parameter_names": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "data_queries": {
            "cube": {
                "link": {
                    "href": "http://srv/collections/test/cube",
                    "variables": {"output_formats": ["CoverageJSON"]},
                }
            }
        },
    }


def _full_payload() -> dict[str, Any]:
    """Rich payload with temporal.values, vertical, CRS list, instances link."""
    return {
        "id": "msg_frm",
        "title": "MSG FRM",
        "description": "Fire risk",
        "crs": [
            "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            "http://www.opengis.net/def/crs/EPSG/0/4326",
        ],
        "output_formats": ["CoverageJSON", "GeoJSON"],
        "extent": {
            "spatial": {
                "bbox": [[10.0, 40.0, 11.0, 41.0]],
                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            },
            "temporal": {
                "interval": [["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"]],
                "values": ["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"],
            },
            "vertical": {
                "interval": [[100.0, 1000.0]],
                "values": [100.0, 500.0, 1000.0],
                "vrs": "EPSG:5714",
            },
        },
        "parameter_names": {
            "FWI": {
                "type": "Parameter",
                "unit": {"symbol": {"value": "-"}},
                "observedProperty": {
                    "id": "FWI",
                    "label": {"en": "Fire Weather Index"},
                },
                "measurementType": {"method": "mean"},
            }
        },
        "data_queries": {
            "cube": {
                "link": {
                    "href": "http://srv/collections/msg_frm/cube",
                    "rel": "data",
                    "type": "application/prs.coverage+json",
                    "variables": {
                        "output_formats": ["CoverageJSON", "GeoJSON"],
                        "default_output_format": "CoverageJSON",
                        "crs_details": [
                            {"crs": "CRS84", "wkt": "..."},
                            {"crs": "EPSG:4326", "wkt": "..."},
                        ],
                    },
                }
            },
            "instances": {"link": {"href": "http://srv/collections/msg_frm/instances"}},
        },
    }


def test_parse_minimal_metadata() -> None:
    """Minimal valid payload yields a populated CollectionMetadata."""
    meta = parse_collection_metadata(_minimal_payload())
    assert isinstance(meta, CollectionMetadata)
    assert meta.id == "test"
    assert meta.title is None
    assert meta.description is None
    assert isinstance(meta.spatial, SpatialExtent)
    assert meta.spatial.bbox == (0.0, 0.0, 1.0, 1.0)
    assert meta.spatial.crs is None
    assert meta.temporal is None
    assert meta.vertical is None
    assert meta.crs_options == ()
    assert "p" in meta.parameters
    assert isinstance(meta.parameters["p"], ParameterDefinition)
    assert isinstance(meta.cube_link, CubeLink)
    assert meta.cube_link.href == "http://srv/collections/test/cube"
    assert meta.cube_link.output_formats == ("CoverageJSON",)
    assert meta.instances_link is None


def test_parse_full_metadata() -> None:
    """Rich payload populates temporal, vertical, crs_options."""
    meta = parse_collection_metadata(_full_payload())
    assert meta.id == "msg_frm"
    assert meta.title == "MSG FRM"
    assert meta.description == "Fire risk"
    assert meta.spatial.bbox == (10.0, 40.0, 11.0, 41.0)
    assert meta.spatial.crs == "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
    assert isinstance(meta.temporal, TemporalExtent)
    assert meta.temporal.interval == (
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
    )
    assert meta.temporal.values == (
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
    )
    assert isinstance(meta.vertical, VerticalExtent)
    assert meta.vertical.interval == (100.0, 1000.0)
    assert meta.vertical.values == (100.0, 500.0, 1000.0)
    assert meta.vertical.vrs == "EPSG:5714"
    assert meta.crs_options == (
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "http://www.opengis.net/def/crs/EPSG/0/4326",
    )
    fwi = meta.parameters["FWI"]
    assert fwi.id == "FWI"
    assert fwi.unit == "-"
    assert fwi.standard_name == "FWI"
    assert fwi.long_name == "Fire Weather Index"
    assert fwi.cell_methods == "mean"
    assert meta.cube_link.default_output_format == "CoverageJSON"


def test_cube_link_crs_options() -> None:
    """crs_details list maps to cube_link.crs_options tuple of crs strings."""
    meta = parse_collection_metadata(_full_payload())
    assert meta.cube_link.crs_options == ("CRS84", "EPSG:4326")


def test_missing_id_raises() -> None:
    """Missing 'id' -> EdrMetadataError mentioning 'id'."""
    payload = _minimal_payload()
    del payload["id"]
    with pytest.raises(EdrMetadataError, match="id"):
        parse_collection_metadata(payload)


def test_missing_cube_href_raises() -> None:
    """Missing data_queries.cube.link.href -> EdrMetadataError mentioning 'cube'."""
    payload = _minimal_payload()
    payload["data_queries"] = {}
    with pytest.raises(EdrMetadataError, match=r"(?i)cube"):
        parse_collection_metadata(payload)


def test_missing_spatial_bbox_raises() -> None:
    """Missing extent.spatial.bbox -> EdrMetadataError."""
    payload = _minimal_payload()
    payload["extent"] = {"spatial": {}}
    with pytest.raises(EdrMetadataError, match=r"(?i)bbox"):
        parse_collection_metadata(payload)


def test_missing_parameter_names_raises() -> None:
    """Missing parameter_names -> EdrMetadataError."""
    payload = _minimal_payload()
    del payload["parameter_names"]
    with pytest.raises(EdrMetadataError, match="parameter_names"):
        parse_collection_metadata(payload)


def test_multiple_bboxes_raises() -> None:
    """Bbox list with >1 entry -> EdrMetadataError mentioning 'bbox'."""
    payload = _minimal_payload()
    payload["extent"]["spatial"]["bbox"] = [[0.0, 0.0, 1.0, 1.0], [10.0, 10.0, 11.0, 11.0]]
    with pytest.raises(EdrMetadataError, match=r"(?i)bbox|disjoint|multiple"):
        parse_collection_metadata(payload)


def test_cube_url_no_instance() -> None:
    """cube_url with instance=None returns canonical absolute href."""
    meta = parse_collection_metadata(_full_payload())
    assert (
        cube_url(meta, instance=None, base_url="http://srv")
        == "http://srv/collections/msg_frm/cube"
    )


def test_cube_url_with_instance() -> None:
    """cube_url with instance derives /instances/<id>/cube."""
    meta = parse_collection_metadata(_full_payload())
    assert (
        cube_url(meta, instance="f024", base_url="http://srv")
        == "http://srv/collections/msg_frm/instances/f024/cube"
    )


def test_cube_url_nonstandard_href_raises() -> None:
    """Cube href not ending in /cube -> EdrMetadataError when instance requested."""
    payload = _minimal_payload()
    payload["data_queries"]["cube"]["link"]["href"] = "http://srv/data/query"
    meta = parse_collection_metadata(payload)
    with pytest.raises(EdrMetadataError, match=r"(?i)non-standard|cube"):
        cube_url(meta, instance="f024", base_url="http://srv")


def test_parameter_missing_observed_property() -> None:
    """Parameter without observedProperty yields standard_name=None, long_name=None."""
    payload = _minimal_payload()
    payload["parameter_names"] = {"x": {"type": "Parameter", "unit": {"symbol": {"value": "K"}}}}
    meta = parse_collection_metadata(payload)
    p = meta.parameters["x"]
    assert p.standard_name is None
    assert p.long_name is None
    assert p.unit == "K"


def test_parameter_missing_unit_symbol() -> None:
    """Parameter with unit dict lacking symbol.value yields unit=None."""
    payload = _minimal_payload()
    payload["parameter_names"] = {
        "x": {
            "type": "Parameter",
            "unit": {"label": {"en": "Kelvin"}},
            "observedProperty": {"id": "x", "label": {"en": "x"}},
        }
    }
    meta = parse_collection_metadata(payload)
    assert meta.parameters["x"].unit is None
    assert meta.parameters["x"].long_name == "x"


def test_instances_link_extracted() -> None:
    """Payload with data_queries.instances.link.href populates instances_link."""
    meta = parse_collection_metadata(_full_payload())
    assert meta.instances_link == "http://srv/collections/msg_frm/instances"


def test_cube_url_relative_href() -> None:
    """Relative cube href is resolved against base_url."""
    payload = _minimal_payload()
    payload["data_queries"]["cube"]["link"]["href"] = "/collections/test/cube"
    meta = parse_collection_metadata(payload)
    assert (
        cube_url(meta, instance=None, base_url="http://srv") == "http://srv/collections/test/cube"
    )


def test_missing_extent_raises() -> None:
    """Missing 'extent' -> EdrMetadataError mentioning 'extent'."""
    payload = _minimal_payload()
    del payload["extent"]
    with pytest.raises(EdrMetadataError, match="extent"):
        parse_collection_metadata(payload)


def test_temporal_with_empty_interval_returns_none() -> None:
    """Temporal block with empty interval list yields temporal=None."""
    payload = _minimal_payload()
    payload["extent"]["temporal"] = {"interval": [], "values": []}
    meta = parse_collection_metadata(payload)
    assert meta.temporal is None


def test_vertical_with_empty_interval_returns_none() -> None:
    """Vertical block with empty interval list yields vertical=None."""
    payload = _minimal_payload()
    payload["extent"]["vertical"] = {"interval": [], "values": []}
    meta = parse_collection_metadata(payload)
    assert meta.vertical is None


def test_dataclasses_are_frozen() -> None:
    """All dataclasses are frozen (immutable value objects)."""
    meta = parse_collection_metadata(_minimal_payload())
    with pytest.raises(FrozenInstanceError):
        meta.id = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        meta.spatial.bbox = (1.0, 2.0, 3.0, 4.0)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        meta.cube_link.href = "x"  # type: ignore[misc]
