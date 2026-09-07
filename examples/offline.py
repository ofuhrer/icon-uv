"""Small, credential-free calculation using SYNTHETIC inputs and the real UV table.

This demonstrates file formats and API composition. It is not an actual forecast
or a scientific validation case. Run from the repository with:
    uv run --no-sync python examples/offline.py --output-dir work/offline
"""

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

from icon_uv import PointLocation, compute_grid, compute_points, export_daily_file
from icon_uv.data import load_cams, write_netcdf
from icon_uv.radiation import solar_geometry


def synthetic_inputs():
    """Return explicitly synthetic normalized ICON and CAMS datasets."""
    starts = np.arange(np.datetime64("2026-09-07T00", "h"),
                       np.datetime64("2026-09-09T00", "h"), np.timedelta64(1, "h"))
    times = (starts + np.timedelta64(30, "m")).astype("datetime64[ns]")
    shape = (len(times), 1)
    zenith, _, _ = solar_geometry(times, 46.95, 7.44)
    icon = xr.Dataset(
        {"sw_down": (("time", "cell"), 700 * np.maximum(np.cos(np.deg2rad(zenith)), 0)[:, None]),
         "pressure_pa": (("time", "cell"), np.full(shape, 95000.)),
         "sw_albedo": (("time", "cell"), np.full(shape, .15)),
         "snow_fraction": (("time", "cell"), np.zeros(shape)),
         "time_bounds": (("time", "bounds"), np.column_stack([times - np.timedelta64(30, "m"),
                                                               times + np.timedelta64(30, "m")]))},
        coords={"time": times, "cell": [0], "latitude": ("cell", [46.95]),
                "longitude": ("cell", [7.44]), "altitude_m": ("cell", [540.])},
        attrs={"forecast_reference_time": "2026-09-07T00:00:00Z",
               "grid_uuid": "synthetic-single-cell", "source": "SYNTHETIC demonstration; not a forecast"},
    )
    for field, units in (("sw_down", "W m-2"), ("pressure_pa", "Pa"),
                         ("sw_albedo", "1"), ("snow_fraction", "1")):
        icon[field].attrs["units"] = units
    icon.time.attrs["bounds"] = "time_bounds"
    cams_times = np.arange(np.datetime64("2026-09-07T00", "h"),
                           np.datetime64("2026-09-09T03", "h"), np.timedelta64(3, "h"))
    cams = xr.Dataset(
        {"ozone_du": (("time", "latitude", "longitude"), np.full((len(cams_times), 2, 2), 310.)),
         "aod550": (("time", "latitude", "longitude"), np.full((len(cams_times), 2, 2), .12))},
        coords={"time": cams_times.astype("datetime64[ns]"),
                "latitude": [46., 48.], "longitude": [7., 8.]},
        attrs={"forecast_reference_time": "2026-09-06T12:00:00Z",
               "source": "SYNTHETIC demonstration; not a forecast"},
    )
    cams.ozone_du.attrs["units"] = "DU"
    cams.aod550.attrs["units"] = "1"
    return icon, cams


def run(output_dir):
    """Save synthetic inputs, reopen them, and calculate grid/point/daily outputs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    icon, cams = synthetic_inputs()
    write_netcdf(icon, output_dir / "icon.nc")
    write_netcdf(cams, output_dir / "cams.nc")
    with xr.open_dataset(output_dir / "icon.nc") as saved_icon:
        grid = compute_grid(saved_icon.load(), load_cams(output_dir / "cams.nc"), samples=12)
    grid.attrs["title"] = "SYNTHETIC UV demonstration; not a forecast"
    grid_path = output_dir / "uv.nc"
    write_netcdf(grid, grid_path)
    locations = [PointLocation("synthetic-bern", 46.95, 7.44, 540,
                               label="SYNTHETIC Bern example")]
    with xr.open_dataset(grid_path) as saved_grid:
        points = compute_points(saved_grid, locations)
    write_netcdf(points, output_dir / "points.nc")
    payload = export_daily_file(grid_path, locations, issued_at="2026-09-07T06:00:00Z",
                                output=output_dir / "daily.json")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("work/offline"))
    args = parser.parse_args()
    result = run(args.output_dir)
    print(f"SYNTHETIC demonstration saved to {args.output_dir}; not a forecast")
    for entry in result["entries"]:
        print(f"{entry['valid_date']}: UVI {entry['uvi']:.2f} ({entry['status']})")
