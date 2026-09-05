"""A cross-model sanity check, explicitly NOT an observation-based skill score.

ECMWF UV documentation defines uvbed/uvbedcs as W/m² dose rates despite the '~'
GRIB units entry. Only those explicit parameter IDs are converted by 40 here.
"""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
from scipy.interpolate import RegularGridInterpolator
import xarray as xr

from .data import grib_messages


def compare(grid, path, output):
    records = {214002: {}, 214003: {}}
    references = set()
    latitude = longitude = None
    for meta, values, coordinates in grib_messages(path):
        parameter = meta["paramId"]
        if parameter not in records or meta["stepType"] != "instant" or coordinates is None:
            raise ValueError("Expected only instantaneous CAMS uvbed/uvbedcs on regular_ll")
        if meta["units"] not in ("~", "W m**-2", "W m-2"):
            raise ValueError("Unexpected CAMS UV encoding")
        references.add((meta["dataDate"], meta["dataTime"]))
        lat, lon = coordinates
        lon = (lon+180) % 360 - 180
        ys, xs = np.unique(lat), np.unique(lon)
        if latitude is not None and (not np.array_equal(latitude, ys) or not np.array_equal(longitude, xs)):
            raise ValueError("Mixed CAMS UV grids")
        latitude, longitude = ys, xs
        data = np.empty((len(ys), len(xs)))
        data[np.searchsorted(ys, lat), np.searchsorted(xs, lon)] = 40*values
        valid = datetime.strptime(f"{meta['validityDate']}{meta['validityTime']:04d}", "%Y%m%d%H%M")
        if valid in records[parameter]:
            raise ValueError("Duplicate CAMS UV valid time")
        records[parameter][valid] = data
    if len(references) != 1 or set(records[214002]) != set(records[214003]):
        raise ValueError("Need one CAMS cycle and matched UV fields")
    times = sorted(records[214002])
    t = np.array(times, dtype="datetime64[s]").astype(float)
    if len(t) < 2 or np.any(np.diff(t) != 3600):
        raise ValueError("Hourly instantaneous CAMS UV fields required")
    result = {"kind": "CAMS cross-model comparison; NOT observational validation",
              "cams_input_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
              "cams_reference": str(next(iter(references))),
              "time_treatment": "CAMS hourly endpoint trapezoid versus reconstructed ICON hourly mean",
              "caveat": "Different cloud fields, elevations, aerosol profiles and albedos; shared CAMS composition is not independent truth",
              "unit_override": "uvbed/uvbedcs *40 per ECMWF UV documentation; raw GRIB unit is '~'"}
    regimes = {"all": np.ones(grid.sizes["cell"], bool),
               "below_800m": grid.altitude_m.values < 800,
               "above_2000m": grid.altitude_m.values > 2000}
    for parameter, name in ((214002, "uvi"), (214003, "clear_sky_uvi")):
        interpolate = RegularGridInterpolator((t, latitude, longitude),
                                             np.array([records[parameter][time] for time in times]), bounds_error=True)
        means = []
        for bounds in grid.time_bounds.values.astype("datetime64[s]").astype(float):
            v = [interpolate(np.column_stack([np.full(grid.sizes["cell"], b), grid.latitude, grid.longitude])) for b in bounds]
            means.append((v[0]+v[1])/2)
        reference = np.array(means)
        own = grid[name].values
        statistics = {}
        for regime, cell_mask in regimes.items():
            mask = (reference >= 1) & cell_mask[None, :] & np.isfinite(own)
            if not np.any(mask):
                statistics[regime] = {"samples": 0}
                continue
            difference = own[mask]-reference[mask]
            statistics[regime] = {"samples": int(mask.sum()), "mean_difference_uvi": float(difference.mean()),
                                  "mae_uvi": float(abs(difference).mean()),
                                  "median_ratio": float(np.median(own[mask]/reference[mask]))}
        result[name] = statistics
    Path(output).write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--grid", type=Path, required=True)
    p.add_argument("--cams-uv", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with xr.open_dataset(args.grid) as d:
        compare(d.load(), args.cams_uv, args.output)
