"""Tests for edr_xarray.coveragejson — Grid CoverageJSON parser."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pytest

from edr_xarray.coveragejson import (
    Axis,
    CoverageData,
    ParameterDef,
    parse_coverage,
)
from edr_xarray.errors import EdrCoverageJsonError, EdrUnsupportedFeatureError


def test_parse_3d_grid_happy_path(sample_cov_grid_3d: dict[str, Any]) -> None:
    """A regular 3D Grid Coverage parses into the expected dataclass."""
    cov = parse_coverage(sample_cov_grid_3d)

    assert isinstance(cov, CoverageData)
    assert cov.axis_names == ("t", "y", "x")
    assert cov.shape == (1, 2, 2)

    assert set(cov.axes.keys()) == {"t", "y", "x"}
    assert isinstance(cov.axes["x"], Axis)
    assert np.allclose(cov.axes["x"].values, [10.0, 11.0])
    assert np.allclose(cov.axes["y"].values, [40.0, 41.0])

    arr = cov.ranges["temperature"]
    assert arr.shape == (1, 2, 2)
    expected = np.array([[[273.15, 274.15], [275.15, 276.15]]])
    assert np.allclose(arr, expected)


def test_regular_interval_axis() -> None:
    """An axis given as start/stop/num is expanded with linspace."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"start": 0.0, "stop": 4.0, "num": 5}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [5],
                "values": [0.0, 1.0, 2.0, 3.0, 4.0],
            }
        },
    }
    cov = parse_coverage(payload)
    assert np.allclose(cov.axes["x"].values, np.array([0.0, 1.0, 2.0, 3.0, 4.0]))


def test_time_axis_parsed_to_datetime64(sample_cov_grid_3d: dict[str, Any]) -> None:
    """ISO time strings (with trailing Z) become datetime64[ns]."""
    cov = parse_coverage(sample_cov_grid_3d)
    t_axis = cov.axes["t"]
    assert t_axis.values.dtype == np.dtype("datetime64[ns]")
    expected = np.array(["2025-01-01T00:00:00"], dtype="datetime64[ns]")
    assert (t_axis.values == expected).all()


def test_time_named_axis_parsed_to_datetime64(sample_cov_grid_3d: dict[str, Any]) -> None:
    """CoverageJSON servers may name the temporal axis 'time' instead of 't'."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["domain"]["axes"]["time"] = payload["domain"]["axes"].pop("t")
    payload["ranges"]["temperature"]["axisNames"] = ["time", "y", "x"]

    cov = parse_coverage(payload)

    assert cov.axes["time"].values.dtype == np.dtype("datetime64[ns]")


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("axisNames", "axisNames"),
        ("shape", "shape"),
        ("values", "values"),
    ],
)
def test_reject_malformed_range_required_fields(
    sample_cov_grid_3d: dict[str, Any],
    field: str,
    message: str,
) -> None:
    """Malformed range array metadata is raised as an edr-xarray error."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    del payload["ranges"]["temperature"][field]

    with pytest.raises(EdrCoverageJsonError, match=message):
        parse_coverage(payload)


def test_reject_malformed_axis_coordinate_spec(sample_cov_grid_3d: dict[str, Any]) -> None:
    """Malformed axis coordinate specs are raised as edr-xarray errors."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["domain"]["axes"]["x"]["values"] = "not-an-array"

    with pytest.raises(EdrCoverageJsonError, match=r"axis 'x'\.values"):
        parse_coverage(payload)


def test_reject_non_object_axis_spec(sample_cov_grid_3d: dict[str, Any]) -> None:
    """Axis specs must be objects."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["domain"]["axes"]["x"] = []

    with pytest.raises(EdrCoverageJsonError, match="axis 'x'"):
        parse_coverage(payload)


def test_reject_bad_time_axis_value(sample_cov_grid_3d: dict[str, Any]) -> None:
    """Malformed temporal coordinate values are wrapped in EdrCoverageJsonError."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["domain"]["axes"]["t"]["values"] = ["not-a-date"]

    with pytest.raises(EdrCoverageJsonError, match=r"axis 't'\.values"):
        parse_coverage(payload)


def test_reject_bad_regular_axis_spec() -> None:
    """Malformed start/stop/num axis specs are wrapped in EdrCoverageJsonError."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"start": "bad", "stop": 4.0, "num": 5}},
        },
        "parameters": {"p": {"type": "Parameter"}},
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [5],
                "values": [0.0, 1.0, 2.0, 3.0, 4.0],
            }
        },
    }

    with pytest.raises(EdrCoverageJsonError, match="start/stop/num"):
        parse_coverage(payload)


def test_reject_non_object_parameter_spec(sample_cov_grid_3d: dict[str, Any]) -> None:
    """Parameter specs must be objects."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["parameters"]["temperature"] = []

    with pytest.raises(EdrCoverageJsonError, match="parameter 'temperature'"):
        parse_coverage(payload)


def test_reject_non_object_range_spec(sample_cov_grid_3d: dict[str, Any]) -> None:
    """Range specs must be objects."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["ranges"]["temperature"] = []

    with pytest.raises(EdrCoverageJsonError, match="range 'temperature'"):
        parse_coverage(payload)


def test_reject_malformed_float_range_values(sample_cov_grid_3d: dict[str, Any]) -> None:
    """Float ranges must contain numeric values or nulls."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["ranges"]["temperature"]["values"][0] = "bad"

    with pytest.raises(EdrCoverageJsonError, match="values is malformed"):
        parse_coverage(payload)


def test_null_values_become_nan(sample_cov_grid_with_nulls: dict[str, Any]) -> None:
    """A null in a float range becomes NaN in the output array."""
    cov = parse_coverage(sample_cov_grid_with_nulls)
    arr = cov.ranges["temperature"]
    assert arr.shape == (1, 2, 2)
    flat = arr.reshape(-1)
    assert flat[0] == 273.15
    assert np.isnan(flat[1])
    assert flat[2] == 275.15
    assert flat[3] == 276.15


def test_multi_parameter() -> None:
    """Two ranges with the same axisNames produce two entries in ranges."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {
                "x": {"values": [10.0, 11.0]},
                "y": {"values": [40.0, 41.0]},
            },
            "referencing": [],
        },
        "parameters": {
            "temperature": {
                "type": "Parameter",
                "observedProperty": {"id": "t", "label": {"en": "t"}},
            },
            "humidity": {
                "type": "Parameter",
                "observedProperty": {"id": "h", "label": {"en": "h"}},
            },
        },
        "ranges": {
            "temperature": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["y", "x"],
                "shape": [2, 2],
                "values": [273.0, 274.0, 275.0, 276.0],
            },
            "humidity": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["y", "x"],
                "shape": [2, 2],
                "values": [50.0, 60.0, 70.0, 80.0],
            },
        },
    }
    cov = parse_coverage(payload)
    assert set(cov.ranges.keys()) == {"temperature", "humidity"}
    assert cov.ranges["temperature"].shape == (2, 2)
    assert cov.ranges["humidity"].shape == (2, 2)
    assert cov.axis_names == ("y", "x")


def test_reject_non_grid_domain(sample_cov_pointseries: dict[str, Any]) -> None:
    """A non-Grid domainType is rejected with EdrUnsupportedFeatureError."""
    with pytest.raises(EdrUnsupportedFeatureError) as exc:
        parse_coverage(sample_cov_pointseries)
    assert "PointSeries" in str(exc.value) or "Grid" in str(exc.value)


def test_reject_tiled_ndarray(sample_cov_tiled: dict[str, Any]) -> None:
    """A TiledNdArray range is rejected with EdrUnsupportedFeatureError."""
    with pytest.raises(EdrUnsupportedFeatureError) as exc:
        parse_coverage(sample_cov_tiled)
    assert "TiledNdArray" in str(exc.value)


def test_reject_inconsistent_axis_names() -> None:
    """Two ranges with different axisNames raise EdrCoverageJsonError."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {
                "x": {"values": [10.0, 11.0]},
                "y": {"values": [40.0, 41.0]},
            },
            "referencing": [],
        },
        "parameters": {
            "a": {
                "type": "Parameter",
                "observedProperty": {"id": "a", "label": {"en": "a"}},
            },
            "b": {
                "type": "Parameter",
                "observedProperty": {"id": "b", "label": {"en": "b"}},
            },
        },
        "ranges": {
            "a": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["y", "x"],
                "shape": [2, 2],
                "values": [1.0, 2.0, 3.0, 4.0],
            },
            "b": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x", "y"],
                "shape": [2, 2],
                "values": [1.0, 2.0, 3.0, 4.0],
            },
        },
    }
    with pytest.raises(EdrCoverageJsonError) as exc:
        parse_coverage(payload)
    assert "axisNames" in str(exc.value)


def test_reject_mismatched_value_count(sample_cov_grid_3d: dict[str, Any]) -> None:
    """A value list whose length doesn't match the shape product is rejected."""
    payload = copy.deepcopy(sample_cov_grid_3d)
    payload["ranges"]["temperature"]["values"] = [1.0, 2.0, 3.0]
    with pytest.raises(EdrCoverageJsonError) as exc:
        parse_coverage(payload)
    msg = str(exc.value)
    assert "3" in msg and "4" in msg


def test_reject_null_in_integer_range() -> None:
    """A null in an integer-typed range is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [10.0, 11.0]}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "integer",
                "axisNames": ["x"],
                "shape": [2],
                "values": [1, None],
            }
        },
    }
    with pytest.raises(EdrCoverageJsonError) as exc:
        parse_coverage(payload)
    assert "integer" in str(exc.value).lower() or "null" in str(exc.value).lower()


def test_parameter_def_extracts_unit_standard_name_long_name(
    sample_cov_grid_3d: dict[str, Any],
) -> None:
    """ParameterDef pulls unit, standard_name, and long_name from the payload."""
    cov = parse_coverage(sample_cov_grid_3d)
    pdef = cov.parameters["temperature"]
    assert isinstance(pdef, ParameterDef)
    assert pdef.name == "temperature"
    assert pdef.unit == "K"
    assert pdef.standard_name == "http://vocab.nerc.ac.uk/standard_name/air_temperature/"
    assert pdef.long_name == "Air temperature"
    assert pdef.cell_methods is None


def test_parameter_def_missing_optional_fields() -> None:
    """ParameterDef fields that lack data are None, not raised."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [10.0]}},
            "referencing": [],
        },
        "parameters": {"p": {"type": "Parameter"}},
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [1],
                "values": [1.0],
            }
        },
    }
    cov = parse_coverage(payload)
    pdef = cov.parameters["p"]
    assert pdef.name == "p"
    assert pdef.unit is None
    assert pdef.standard_name is None
    assert pdef.long_name is None
    assert pdef.cell_methods is None


def test_parameter_def_extracts_cell_methods() -> None:
    """measurementType.method maps onto ParameterDef.cell_methods."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [10.0]}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "measurementType": {"method": "mean", "period": "PT1H"},
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [1],
                "values": [1.0],
            }
        },
    }
    cov = parse_coverage(payload)
    assert cov.parameters["p"].cell_methods == "mean"


def test_shape_mismatch_with_axis_length() -> None:
    """If shape[i] disagrees with len(axes[axis_names[i]]), reject."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [10.0, 11.0, 12.0]}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [2],
                "values": [1.0, 2.0],
            }
        },
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_integer_range_without_nulls() -> None:
    """An integer dataType without nulls is preserved as an integer array."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0, 1.0]}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "integer",
                "axisNames": ["x"],
                "shape": [2],
                "values": [3, 5],
            }
        },
    }
    cov = parse_coverage(payload)
    arr = cov.ranges["p"]
    assert arr.shape == (2,)
    assert int(arr[0]) == 3
    assert int(arr[1]) == 5


def test_reject_axis_without_values_or_range() -> None:
    """An axis with neither 'values' nor start/stop/num is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [1],
                "values": [1.0],
            }
        },
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_unknown_range_type() -> None:
    """A range type that is neither NdArray nor TiledNdArray is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0]}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "Mystery",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [1],
                "values": [1.0],
            }
        },
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_payload_missing_domain() -> None:
    """A payload without a 'domain' object is rejected."""
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage({"parameters": {}, "ranges": {}})


def test_reject_payload_missing_axes() -> None:
    """A domain without 'axes' is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {"type": "Domain", "domainType": "Grid", "referencing": []},
        "parameters": {},
        "ranges": {},
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_payload_missing_parameters() -> None:
    """A payload without 'parameters' is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0]}},
            "referencing": [],
        },
        "ranges": {},
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_payload_missing_ranges() -> None:
    """A payload without 'ranges' is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0]}},
            "referencing": [],
        },
        "parameters": {},
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_empty_ranges() -> None:
    """A payload with an empty 'ranges' object is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0]}},
            "referencing": [],
        },
        "parameters": {},
        "ranges": {},
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_inconsistent_shape_between_ranges() -> None:
    """Two ranges with the same axisNames but different shape are rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0, 1.0]}},
            "referencing": [],
        },
        "parameters": {
            "a": {
                "type": "Parameter",
                "observedProperty": {"id": "a", "label": {"en": "a"}},
            },
            "b": {
                "type": "Parameter",
                "observedProperty": {"id": "b", "label": {"en": "b"}},
            },
        },
        "ranges": {
            "a": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [2],
                "values": [1.0, 2.0],
            },
            "b": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["x"],
                "shape": [3],
                "values": [1.0, 2.0, 3.0],
            },
        },
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


def test_reject_axis_referenced_by_range_not_in_domain() -> None:
    """An axisNames entry that is not present in domain.axes is rejected."""
    payload = {
        "type": "Coverage",
        "domain": {
            "type": "Domain",
            "domainType": "Grid",
            "axes": {"x": {"values": [0.0, 1.0]}},
            "referencing": [],
        },
        "parameters": {
            "p": {
                "type": "Parameter",
                "observedProperty": {"id": "p", "label": {"en": "p"}},
            }
        },
        "ranges": {
            "p": {
                "type": "NdArray",
                "dataType": "float",
                "axisNames": ["y"],
                "shape": [2],
                "values": [1.0, 2.0],
            }
        },
    }
    with pytest.raises(EdrCoverageJsonError):
        parse_coverage(payload)


@pytest.fixture()
def sample_cov_pointseries() -> dict[str, Any]:
    """Minimal PointSeries Coverage for non-Grid rejection tests."""
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "data" / "cov_pointseries.json").read_text())


@pytest.fixture()
def sample_cov_tiled() -> dict[str, Any]:
    """Minimal TiledNdArray Coverage for unsupported-range rejection tests."""
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "data" / "cov_tiled.json").read_text())
