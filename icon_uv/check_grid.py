"""Reproducible output checks, including reconstruction of the SW forcing.

This checks numerical/data integrity, not forecast accuracy against observations.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr

from .ensemble import member_ids
from .products import _check_icon, _sample_times
from .radiation import FLAG_MEANINGS, RadiationTable, solar_geometry


def check_grid(grid, table=None, *, seed=20260905, cells=512):
    ids = member_ids(grid)
    if ids is not None:
        reports = {str(m): check_grid(grid.sel(member=m, drop=True), table, seed=seed, cells=cells) for m in ids}
        return {'passed': all(r['passed'] for r in reports.values()), 'member_count': len(ids), 'members': reports}
    _check_icon(grid, allow_missing="minimum_member_fraction" in grid.attrs or "ensemble_members" in grid.attrs)
    table = RadiationTable() if table is None else table
    if grid.attrs.get("radiation_table_sha256") != table.sha256:
        raise ValueError("Grid/table hash mismatch")
    missing = (grid.quality_flag.values & 128) != 0
    for name in ("uvi", "clear_sky_uvi", "erythemal_direct", "erythemal_diffuse",
                 "uvi_sample_max", "effective_cloud_tau550", "cloud_scale"):
        if (not np.array_equal(np.isnan(grid[name]), missing) or np.any(np.isinf(grid[name])) or np.any(grid[name] < 0)):
            raise ValueError(f"Invalid output {name}")
    identity = abs(grid.uvi-40*(grid.erythemal_direct+grid.erythemal_diffuse)).values
    if not np.allclose(grid.uvi, 40*(grid.erythemal_direct+grid.erythemal_diffuse), rtol=2e-6, atol=1e-6, equal_nan=True):
        raise ValueError("UVI/component identity failed")
    if np.any(grid.uvi_sample_max+1e-6 < grid.uvi):
        raise ValueError("Sample maximum below hourly mean")
    rng = np.random.default_rng(seed)
    indices = np.sort(rng.choice(grid.sizes["cell"], min(cells, grid.sizes["cell"]), replace=False))
    sampled = grid.isel(cell=indices)
    residuals = []
    for i, bounds in enumerate(grid.time_bounds.values):
        d = sampled.isel(time=i)
        d = d.isel(cell=np.flatnonzero((d.quality_flag.values & 128) == 0))
        if not d.sizes["cell"]:
            continue
        times = _sample_times(bounds, int(grid.attrs["solar_samples_per_hour"]))
        z, _, distance = solar_geometry(times[:, None], d.latitude.values, d.longitude.values)
        f = table.at(z, d.ozone_du.values, d.pressure_pa.values, d.aod550.values,
                     d.sw_albedo.values, d.effective_cloud_tau550.values)
        reconstructed = (f[..., :2].sum(axis=-1)*distance).mean(axis=0)*d.cloud_scale.values
        valid = (d.quality_flag.values & 4) == 0
        residuals.extend((reconstructed-d.sw_down.values)[valid].tolist())
        if np.any(d.uvi.values[np.all(z >= 90, axis=0)] != 0):
            raise ValueError("Nonzero UVI at sampled night cells")
    maximum_residual = float(np.max(np.abs(residuals))) if residuals else 0.
    if maximum_residual > .001:
        raise ValueError(f"SW reconstruction residual {maximum_residual} W/m2 exceeds 0.001")
    flags = grid.quality_flag.values
    flag_counts = {str(bit): {"meaning": meaning, "cell_hours": int(((flags & bit) != 0).sum()),
                             "cell_hours_uvi_ge1": int((((flags & bit) != 0) & (grid.uvi.values >= 1)).sum())}
                   for bit, meaning in FLAG_MEANINGS.items()}
    return {"kind": "grid integrity check; NOT observational validation", "passed": True,
            "table_sha256": table.sha256, "seed": seed, "sampled_cells": len(indices),
            "cells": grid.sizes["cell"], "hours": grid.sizes["time"],
            "time_start_utc": str(grid.time_bounds.values[0, 0]),
            "time_end_utc": str(grid.time_bounds.values[-1, 1]),
            "icon_reference_time": grid.attrs["forecast_reference_time"],
            "cams_reference_time": grid.attrs["cams_reference_time"],
            "bbox": json.loads(grid.attrs["bbox"]),
            "compute_seconds": grid.attrs["compute_seconds"],
            "uvi_range": [float(grid.uvi.min()), float(grid.uvi.max())] if np.isfinite(grid.uvi).any() else [None, None],
            "missing_cell_hours": int(missing.sum()),
            "maximum_uvi_component_residual": float(np.nanmax(identity)) if np.isfinite(identity).any() else 0.,
            "sw_reconstruction_samples": len(residuals),
            "maximum_sw_reconstruction_residual_w_m2": maximum_residual,
            "quality_flags": flag_counts}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with xr.open_dataset(args.grid) as ds:
        report = check_grid(ds.load())
    report["file_bytes"] = args.grid.stat().st_size
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
