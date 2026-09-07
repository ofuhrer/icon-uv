"""Published contracts remain stable and select correctly for actual payloads."""

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest
import xarray as xr

from icon_uv.schema import SCHEMA_VERSIONS, load_schema, validate_daily


ROOT = Path(__file__).resolve().parents[1]


def load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("version", SCHEMA_VERSIONS)
def test_packaged_schemas_are_valid_and_selected_from_payload(version):
    schema = load_schema(version)
    assert load_schema({"schema_version": version}) == schema
    jsonschema.Draft202012Validator.check_schema(schema)
    schema["properties"].clear()
    assert load_schema(version)["properties"]  # callers do not share mutation


@pytest.mark.parametrize("version", [None, {}, [], 3, "v3", "../../README.md", "daily-uv-v99"])
def test_unknown_schema_versions_fail_clearly(version):
    with pytest.raises(ValueError, match="Unsupported daily schema"):
        load_schema(version)


def test_generated_schemas_match_published_artifacts():
    generator = load_script(ROOT / "tools/generate_schemas.py")
    for version, schema in generator.generate_schemas().items():
        assert (generator.SCHEMA_DIR / f"{version}.schema.json").read_text() == json.dumps(schema, indent=2) + "\n"


def test_offline_saved_input_example_uses_real_table(tmp_path):
    example = load_script(ROOT / "examples/offline.py")
    payload = example.run(tmp_path)
    validate_daily(payload)
    assert len(payload["entries"]) == 2
    assert all(entry["status"] == "ok" and 0 < entry["uvi"] < 20 for entry in payload["entries"])
    with xr.open_dataset(tmp_path / "uv.nc") as grid:
        assert grid.sizes == {"time": 48, "cell": 1, "bounds": 2}
        assert "SYNTHETIC" in grid.attrs["title"]
        assert grid.uvi.max() > 0
        assert len(grid.attrs["radiation_table_sha256"]) == 64
    with pytest.raises(jsonschema.ValidationError):
        validate_daily({**payload, "issued_at": "not-a-date"})


@pytest.mark.parametrize("ensemble", [False, True])
def test_shared_point_publication_validates_with_v4(tmp_path, ensemble):
    from icon_uv.daily import compute_daily, daily_payload
    from icon_uv.locations import PointLocation, load_locations
    from icon_uv.products import compute_grid

    example = load_script(ROOT / "examples/offline.py")
    icon, cams = example.synthetic_inputs()
    grid = compute_grid(icon, cams)
    if ensemble:
        grid = grid.expand_dims(member=[0, 1])
    locations = load_locations([
        PointLocation("native", 46.95, 7.44, 540, treatment="native"),
        PointLocation("adjusted", 46.95, 7.44, 1000,
                      treatment="adjusted", uv_albedo=.05, horizon_degrees=(0.,) * 4),
    ])
    result = compute_daily(grid, locations, dates=["2026-09-07"])
    payload = daily_payload(result, issued_at="2026-09-07T06:00:00Z",
                               input_sha256="0" * 64, schema_version="daily-uv-v4")
    assert payload["schema_version"] == "daily-uv-v4"
    assert all(entry["uvi"] > 0 for entry in payload["entries"])
    assert all("support_uvi_range" in entry and "support_uvi_median" in entry
               and "native_uvi_range" not in entry and "native_uvi_median" not in entry
               for entry in payload["entries"])
    validate_daily(payload)
    broken = json.loads(json.dumps(payload))
    del broken["entries"][1]["location"]["uv_albedo"]
    with pytest.raises(jsonschema.ValidationError):
        validate_daily(broken)
    if ensemble:
        del payload["entries"][0]["ensemble"]
        with pytest.raises(jsonschema.ValidationError):
            validate_daily(payload)
        # The documented default ensemble workflow must select v3, not v1.
        from icon_uv.daily import export_daily
        legacy = {"catalog_version": 1, "entries": [{"id": "bern", "kind": "town",
                  "latitude": 46.95, "longitude": 7.44, "altitude_m": 540}]}
        default = export_daily(grid, legacy, issued_at="2026-09-07T06:00:00Z", input_sha256="0" * 64)
        assert default["schema_version"] == "daily-uv-v3"
        validate_daily(default)


def test_v5_accepts_inherited_albedo_without_loosening_published_v4(tmp_path):
    from icon_uv.daily import compute_daily, daily_payload, write_daily_json
    from icon_uv.locations import PointLocation
    from icon_uv.products import compute_grid

    example = load_script(ROOT / "examples/offline.py")
    icon, cams = example.synthetic_inputs()
    result = compute_daily(compute_grid(icon, cams), [PointLocation("bern", 46.95, 7.44, 540)],
                           dates=["2026-09-07"])
    payload = write_daily_json(result, tmp_path / "v5.json", issued_at="2026-09-07T06:00:00Z",
                               input_sha256="0" * 64)
    assert payload["schema_version"] == "daily-uv-v5"
    assert "uv_albedo" not in payload["entries"][0]["location"]
    validate_daily(payload)
    old = json.loads(json.dumps(payload))
    old.update(schema_version="daily-uv-v4", contract_sha256=load_schema("daily-uv-v4")["properties"]["contract_sha256"]["const"])
    with pytest.raises(jsonschema.ValidationError):
        validate_daily(old)
    with pytest.raises(ValueError, match="albedo"):
        daily_payload(result, issued_at="2026-09-07T06:00:00Z",
                      input_sha256="0" * 64, schema_version="daily-uv-v4")
