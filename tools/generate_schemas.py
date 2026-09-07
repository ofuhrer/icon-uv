"""Generate v2/v3/v4 from the published v1 base; preserve public contracts.

Run ``uv run python tools/generate_schemas.py --check`` in CI, or omit --check
after deliberately changing a contract. Runtime consumers load standalone JSON.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "icon_uv" / "data"


def generate_schemas():
    base = json.loads((SCHEMA_DIR / "daily-uv-v1.schema.json").read_text())
    v2 = deepcopy(base)
    v2["title"] = "Daily UV forecast product v2"
    v2["description"] = "Four local dates or all forecast daylight dates. Per-entry support, rounding and missing-value rules match v1. Date offsets and pairing require semantic checks."
    v2["required"].append("valid_dates")
    props = v2["properties"]
    props["schema_version"]["const"] = "daily-uv-v2"
    props["contract_sha256"]["const"] = "804568736f489e914b8c63ac99b2857154ed616a644431efbe04df36e524d422"
    props["entries"]["minItems"] = 1
    props["valid_dates"] = {"type": "array", "minItems": 1, "uniqueItems": True,
                           "items": {"type": "string", "format": "date"}}
    v2["$defs"]["entry"]["properties"]["day"] = {"type": "integer", "minimum": 0}

    v3 = deepcopy(v2)
    v3["title"] = "Daily UV ensemble product v3"
    v3["description"] = "Per-member daily/spatial products, then ensemble quantile; minimum contributing fraction and counts explicit. Native ranges and peak times span available members and cells."
    v3["required"].append("ensemble")
    props = v3["properties"]
    props["schema_version"]["const"] = "daily-uv-v3"
    props["contract_sha256"]["const"] = "639b2c100c246aec6e1ab0bf338419e433b4f086c8e5d37bcb3f12993c41456f"
    member_ids = {"type": "array", "minItems": 1, "uniqueItems": True,
                  "items": {"type": "integer", "minimum": 0, "maximum": 20}}
    member_count = {"type": "integer", "minimum": 1, "maximum": 21}
    probability = {"type": "number", "minimum": 0, "maximum": 1}
    positive_uv = {"type": "number", "minimum": 0}
    props["ensemble"] = {
        "type": "object",
        "required": ["member_ids", "member_count", "deterministic_quantile", "reduction",
                     "quantile_method", "uncertainty_scope", "requested_member_ids",
                     "minimum_member_fraction", "required_member_count"],
        "properties": {
            "member_ids": deepcopy(member_ids), "member_count": deepcopy(member_count),
            "deterministic_quantile": deepcopy(probability),
            "reduction": {"const": "quantile_of_member_daily_products"},
            "quantile_method": {"const": "linear"}, "uncertainty_scope": {"type": "string"},
            "requested_member_ids": deepcopy(member_ids),
            "minimum_member_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
            "required_member_count": deepcopy(member_count),
        },
    }
    entry = v3["$defs"]["entry"]
    entry["properties"]["ensemble"] = {
        "type": "object",
        "required": ["member_uvi", "p10", "p50", "p90", "probability_uvi_ge", "valid_member_count"],
        "properties": {
            "member_uvi": {"type": "array", "minItems": 1, "maxItems": 21,
                           "items": {"type": ["number", "null"], "minimum": 0}},
            **{key: deepcopy(positive_uv) for key in ("p10", "p50", "p90")},
            "probability_uvi_ge": {"type": "object", "required": ["3", "6", "8", "11"],
                                   "properties": {key: deepcopy(probability) for key in ("3", "6", "8", "11")}},
            "valid_member_count": deepcopy(member_count),
        },
    }
    # The available-entry branch carries ensemble detail. A quantile of member
    # peaks has a time range, rather than the single peak required by CTRL.
    available = entry["allOf"][0]["else"]
    available["required"].append("ensemble")
    available["allOf"][0]["then"]["required"].remove("peak_window_start_utc")
    entry["allOf"][2]["then"]["properties"]["reasons"].pop("contains")
    v4 = deepcopy(v3)
    v4["title"] = "Daily UV location product v4"
    v4["description"] = "Explicit native or adjusted point treatment, regional memberwise spatial support, arbitrary local dates and ambient or terrain-screened UV. Ensemble summaries are present for ensemble inputs."
    v4["required"].remove("ensemble")
    v4["required"].append("uv_geometry")
    props = v4["properties"]
    props["schema_version"]["const"] = "daily-uv-v4"
    props["contract_sha256"]["const"] = hashlib.sha256(b"daily-uv-v4: explicit location treatment; memberwise spatial support; arbitrary dates; ambient or terrain-screened UV").hexdigest()
    props["uv_geometry"] = {"enum": ["ambient_horizontal", "terrain_screened"]}
    entry = v4["$defs"]["entry"]
    entry["properties"] = {key.replace("native_uvi_", "support_uvi_"): value
                           for key, value in entry["properties"].items()}
    entry["allOf"][0]["else"]["required"] = [key.replace("native_uvi_", "support_uvi_")
                                            for key in entry["allOf"][0]["else"]["required"]]
    loc = entry["properties"]["location"]
    loc["properties"]["kind"]["enum"].append("point")
    loc["properties"].update({
        "treatment": {"enum": ["native", "adjusted"]},
        "uv_albedo": {"type": "number", "minimum": 0, "maximum": .85},
        "horizon_degrees": {"type": "array", "minItems": 4,
                            "items": {"type": "number", "minimum": 0, "maximum": 90}},
        "maximum_distance_km": {"type": "number", "exclusiveMinimum": 0},
    })
    loc["allOf"].append({"if": {"properties": {"kind": {"const": "point"}}},
                         "then": {"required": ["latitude", "longitude", "treatment"]}})
    loc["allOf"].append({"if": {"required": ["treatment"], "properties": {"treatment": {"const": "adjusted"}}},
                         "then": {"required": ["uv_albedo"]}})
    entry["properties"]["aggregation"]["enum"].append("adjusted_point_daily_maximum")
    entry["properties"]["source_point"]["properties"]["altitude_difference_m"] = {"type": "number"}
    entry["properties"]["ensemble"]["properties"]["member_valid_cells"] = {
        "type": "array", "minItems": 1, "maxItems": 21,
        "items": {"type": "integer", "minimum": 0},
    }
    available = entry["allOf"][0]["else"]
    available["required"].remove("ensemble")
    available["allOf"][0]["if"]["properties"]["location"]["properties"]["kind"] = {"enum": ["town", "point"]}
    # Native points retain their elevation suitability rule; adjusted points
    # expose the actual height change without the native +/-300 m restriction.
    entry["allOf"].append({
        "if": {"properties": {"location": {"properties": {"kind": {"const": "town"}}}}},
        "then": {"properties": {"source_point": {"properties": {
            "altitude_difference_m": {"type": "number", "minimum": -300, "maximum": 300}}}}},
    })
    v4["allOf"] = [{"if": {"required": ["ensemble"]}, "then": {"properties": {
        "entries": {"items": {"if": {"properties": {"status": {"enum": ["ok", "degraded"]}}},
                              "then": {"required": ["ensemble"]}}}}}}]
    return {"daily-uv-v1": base, "daily-uv-v2": v2, "daily-uv-v3": v3, "daily-uv-v4": v4}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts differ")
    args = parser.parse_args()
    for version, schema in generate_schemas().items():
        path = SCHEMA_DIR / f"{version}.schema.json"
        content = json.dumps(schema, indent=2) + "\n"
        if args.check:
            if path.read_text() != content:
                parser.exit(1, f"Schema differs: {path}; run tools/generate_schemas.py\n")
        else:
            path.write_text(content)


if __name__ == "__main__":
    main()
