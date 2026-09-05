"""Exploratory comparison with saved Austrian UV-network public measurements.

Not the calibrated observation API: this display feed has no per-value QC or
documented averaging bounds. No QC-passed status is invented. No POI is recomputed
without local information; this compares the nearest unadjusted native-grid cell.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
import xarray as xr

from .data import utc
from .products import _xyz


def compare(grid, measurements, sites):
    west, south, east, north = json.loads(grid.attrs["bbox"])
    tree = cKDTree(_xyz(grid.latitude.values, grid.longitude.values))
    results = {}
    for site in sites:
        name = site["name"]
        if not (west <= site["longitude"] <= east and south <= site["latitude"] <= north):
            continue
        data = measurements.get(name, {}).get("uve")
        if data is None:
            continue
        if data.get("unit") != "UV-Index" or len(data["ts"]) != len(data["measurement"]):
            raise ValueError("Expected timestamped UV-Index measurements")
        times = [np.datetime64(utc(t).replace(tzinfo=None), "ns") for t in data["ts"]]
        if len(set(times)) != len(times):
            raise ValueError("Duplicate observation timestamps")
        values = dict(zip(times, data["measurement"]))
        distance, cell = tree.query(_xyz([site["latitude"]], [site["longitude"]]))
        cell = int(cell[0])
        distance = float(2*6371*np.arcsin(min(float(distance[0])/2, 1)))
        if distance > 10:
            continue
        pairs = []
        for i, bounds in enumerate(grid.time_bounds.values):
            stamps = bounds[0] + np.array([15, 45])*np.timedelta64(1, "m")
            if any(t not in values or values[t] is None for t in stamps):
                continue
            observed = np.array([values[t] for t in stamps], float)
            if np.any(~np.isfinite(observed)) or np.any(observed < 0):
                continue
            pairs.append({"time_utc": str(grid.time.values[i]),
                          "reported_pair_mean_uvi": float(observed.mean()),
                          "forecast_hourly_mean_uvi": float(grid.uvi.values[i, cell]),
                          "forecast_flag": int(grid.quality_flag.values[i, cell])})
        summary = {"matched_hours": len(pairs), "source_latitude": site["latitude"],
                   "source_longitude": site["longitude"], "source_altitude_m": site["altitude"],
                   "model_altitude_m": float(grid.altitude_m.values[cell]),
                   "source_cell": int(grid.cell.values[cell]), "distance_km": distance, "pairs": pairs}
        selected = [p for p in pairs if p["reported_pair_mean_uvi"] >= 1]
        summary["hours_reported_uvi_ge1"] = len(selected)
        if selected:
            error = np.array([p["forecast_hourly_mean_uvi"]-p["reported_pair_mean_uvi"] for p in selected])
            summary.update(bias_uvi=float(error.mean()), mae_uvi=float(abs(error).mean()),
                           rmse_uvi=float(np.sqrt((error**2).mean())))
        results[name] = summary
    return {"kind": "exploratory public-measurement comparison, NOT calibrated forecast qualification",
            "source": "https://uv-data.i-med.ac.at/public/",
            "qc_status": "Public display values; no per-value QC/calibration metadata supplied",
            "time_assumption": "Mean of reported values at :15 and :45 approximates the hourly mean; provider averaging bounds unconfirmed",
            "spatial_treatment": "Nearest native-grid cell, no altitude/horizon/albedo correction; not a local POI forecast",
            "icon_reference_time": grid.attrs["forecast_reference_time"],
            "cams_reference_time": grid.attrs["cams_reference_time"],
            "table_sha256": grid.attrs["radiation_table_sha256"], "sites": results}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, required=True)
    p.add_argument("--measurements", type=Path, required=True)
    p.add_argument("--sites", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with xr.open_dataset(args.grid) as d:
        result = compare(d.load(), json.loads(args.measurements.read_text()), json.loads(args.sites.read_text()))
    result["measurements_sha256"] = hashlib.sha256(args.measurements.read_bytes()).hexdigest()
    result["sites_sha256"] = hashlib.sha256(args.sites.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({**result, "sites": {k: {a: b for a, b in v.items() if a != "pairs"}
                                          for k, v in result["sites"].items()}}, indent=2))
