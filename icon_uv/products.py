"""Gridded numerical products and caller-owned POI geometry. No HTTP server."""
from dataclasses import dataclass
import json
import time

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree
import xarray as xr

from . import __version__
from .ensemble import member_ids, map_members
from .data import utc
from .radiation import FLAG_MEANINGS, RadiationTable, solar_geometry


def _check_icon(ds, *, allow_missing=False):
    for name, units in (("pressure_pa", "Pa"), ("sw_down", "W m-2"),
                        ("sw_albedo", "1"), ("snow_fraction", "1")):
        if name not in ds or ds[name].dims != ("time", "cell") or ds[name].attrs.get("units") != units:
            raise ValueError(f"ICON contract: {name}(time,cell) [{units}] required")
        if np.any(np.isinf(ds[name])) or (not allow_missing and not np.all(np.isfinite(ds[name]))):
            raise ValueError(f"Missing ICON {name}")
    for name in ("latitude", "longitude", "altitude_m"):
        if ds[name].dims != ("cell",) or not np.all(np.isfinite(ds[name])):
            raise ValueError(f"Invalid ICON {name}")
    if np.any(abs(ds.latitude) > 90) or np.any(abs(ds.longitude) > 180):
        raise ValueError("ICON coordinates must be geographic degrees")
    if len(np.unique(ds.cell)) != ds.sizes["cell"]:
        raise ValueError("Duplicate ICON cell identifiers")
    for name in ("sw_albedo", "snow_fraction"):
        if np.any((ds[name] < 0) | (ds[name] > 1)):
            raise ValueError(f"Invalid {name}")
    if np.any(ds.sw_down < 0):
        raise ValueError("Negative SW input")
    bounds = ds.time_bounds.values
    if bounds.shape != (ds.sizes["time"], 2) or np.any(np.isnat(bounds)):
        raise ValueError("Missing interval bounds")
    if np.any(bounds[:, 1]-bounds[:, 0] != np.timedelta64(1, "h")):
        raise ValueError("Expected hourly intervals")
    if np.any(bounds[1:, 0] != bounds[:-1, 1]):
        raise ValueError("Non-contiguous hourly intervals")
    if np.any(ds.time.values != bounds[:, 0]+np.timedelta64(30, "m")):
        raise ValueError("time must be interval midpoint")
    utc(ds.attrs["forecast_reference_time"])


def _cams_on_icon(cams, icon):
    for name, units in (("ozone_du", "DU"), ("aod550", "1")):
        if (name not in cams or cams[name].dims != ("time", "latitude", "longitude")
            or cams[name].attrs.get("units") != units or not np.all(np.isfinite(cams[name]))):
            raise ValueError(f"Invalid CAMS {name} contract; expected {units}")
    for dim in ("time", "latitude", "longitude"):
        values = cams[dim].values
        if len(values) < 2 or not np.all(values[1:] > values[:-1]):
            raise ValueError(f"CAMS {dim} must increase with at least two values")
    ref = utc(cams.attrs["forecast_reference_time"])
    icon_ref = utc(icon.attrs["forecast_reference_time"])
    if ref > icon_ref:
        raise ValueError("CAMS cycle is newer than ICON: avoid look-ahead; choose an earlier CAMS cycle")
    if (icon_ref-ref).total_seconds() > 36*3600:
        raise ValueError("CAMS cycle more than 36 hours older than ICON")
    t = cams.time.values.astype("datetime64[s]").astype(float)
    target_t = icon.time.values.astype("datetime64[s]").astype(float)
    if np.any(np.diff(t) > 3*3600):
        raise ValueError("CAMS temporal gap exceeds three hours")
    arrays = {}
    for name in ("ozone_du", "aod550"):
        interpolate = RegularGridInterpolator((t, cams.latitude.values, cams.longitude.values),
                                             cams[name].values, bounds_error=True)
        arrays[name] = np.array([interpolate(np.column_stack([
            np.full(icon.sizes["cell"], v), icon.latitude.values, icon.longitude.values]))
            for v in target_t])
    return arrays


def _sample_times(bounds, samples):
    return bounds[0] + ((np.arange(samples)+.5)*3600/samples).astype("timedelta64[s]")


def compute_grid(icon, cams, table=None, *, chunk_size=2048, samples=4, progress=False):
    """Hourly means on native ICON cells, retaining sufficient state for POIs.

    samples subdivides solar geometry only, not forecast cloud evolution. Default
    snow conversion is experimental and recorded, not inferred UV observations.
    """
    if member_ids(icon) is not None:
        return map_members(compute_grid, icon, cams=cams, table=table,
                           chunk_size=chunk_size, samples=samples, progress=progress)
    _check_icon(icon, allow_missing="minimum_member_fraction" in icon.attrs or "ensemble_members" in icon.attrs)
    if chunk_size < 1 or samples not in (1, 2, 4, 6, 12):
        raise ValueError("Positive chunk size; samples must be 1,2,4,6,12")
    table = RadiationTable() if table is None else table
    composition = _cams_on_icon(cams, icon)
    out = icon.copy(deep=True)
    for name, values in composition.items():
        out[name] = (("time", "cell"), values)
        out[name].attrs["units"] = "DU" if name == "ozone_du" else "1"
    out["uv_albedo"] = .05 + .75*out.snow_fraction
    out.uv_albedo.attrs = {"units": "1", "comment": "EXPERIMENTAL: 0.05+0.75*ICON snow fraction"}
    shape = (out.sizes["time"], out.sizes["cell"])
    names = ("erythemal_direct", "erythemal_diffuse", "uvi", "clear_sky_uvi",
             "uvi_sample_max", "effective_cloud_tau550", "cloud_scale")
    result = {name: np.full(shape, np.nan, dtype=np.float32) for name in names}
    flags = np.full(shape, 128, dtype=np.uint16)
    started = time.monotonic()
    for it, bounds in enumerate(out.time_bounds.values):
        times = _sample_times(bounds, samples)
        for start in range(0, shape[1], chunk_size):
            sl = slice(start, start+chunk_size)
            local = out.isel(time=it, cell=sl)
            valid = np.all([np.isfinite(local[k].values) for k in
                            ('sw_down', 'pressure_pa', 'sw_albedo', 'snow_fraction')], axis=0)
            if not valid.any():
                continue
            target = start + np.flatnonzero(valid)
            local = local.isel(cell=np.flatnonzero(valid))
            z, _, distance = solar_geometry(times[:, None], local.latitude.values[None, :],
                                            local.longitude.values[None, :])
            o, p, a = (local[k].values for k in ("ozone_du", "pressure_pa", "aod550"))
            tau, scale, flag = table.cloud(z, distance, o, p, a,
                                           local.sw_albedo.values, local.sw_down.values)
            uv = table.at(z, o, p, a, local.uv_albedo.values, tau)[..., 2:]
            uv *= distance[..., None] * scale[None, :, None]
            clear = table.at(z, o, p, a, local.uv_albedo.values, 0)[..., 2:]
            clear *= distance[..., None]
            mean = uv.mean(axis=0)
            for name, value in (("erythemal_direct", mean[:, 0]), ("erythemal_diffuse", mean[:, 1]),
                                ("uvi", 40*mean.sum(axis=-1)),
                                ("clear_sky_uvi", 40*clear.sum(axis=-1).mean(axis=0)),
                                ("uvi_sample_max", 40*uv.sum(axis=-1).max(axis=0)),
                                ("effective_cloud_tau550", tau), ("cloud_scale", scale)):
                result[name][it, target] = value
            flags[it, target] = flag
        if progress:
            print(f"UV hour {it+1}/{shape[0]} ({shape[1]} cells); {time.monotonic()-started:.1f}s", flush=True)
    for name, value in result.items():
        out[name] = (("time", "cell"), value)
        out[name].attrs["units"] = "W m-2" if name.startswith("erythemal_") else "1"
        if name in ("erythemal_direct", "erythemal_diffuse", "uvi", "clear_sky_uvi"):
            out[name].attrs["cell_methods"] = "time: mean"
    out.uvi_sample_max.attrs["comment"] = "Maximum of reconstructed solar samples within hour; not actual subhourly cloud maximum"
    out.erythemal_direct.attrs["comment"] = "Direct beam projected onto horizontal surface, not direct normal"
    out["quality_flag"] = (("time", "cell"), flags)
    out.quality_flag.attrs = {"flag_masks": np.array(list(FLAG_MEANINGS), dtype=np.uint16),
                              "flag_meanings": " ".join(FLAG_MEANINGS.values())}
    out.attrs.update({"Conventions": "CF-1.10", "title": "Offline ICON/CAMS gridded UV diagnostic",
                      "status": "EXPERIMENTAL: numerical qualification is not observational validation",
                      "icon_uv_version": __version__, "radiation_table": json.dumps(table.metadata),
                      "radiation_table_sha256": table.sha256,
                      "cams_reference_time": cams.attrs["forecast_reference_time"],
                      "cams_source": cams.attrs.get("source", "caller supplied CAMS"),
                      "cams_input_sha256": cams.attrs.get("input_sha256", "not supplied"),
                      "geometry": "horizontal, open horizon, model surface pressure",
                      "solar_samples_per_hour": samples, "compute_seconds": time.monotonic()-started,
                      "assumptions": "fixed reference profile/H2O/aerosol type; effective uniform liquid cloud; experimental UV snow albedo"})
    return out


@dataclass(frozen=True)
class POI:
    """All local fields are mandatory. Horizon: equally spaced azimuths from north.

    uv_albedo represents effective UV reflectance of local surroundings, not a
    skin/material reflectance. No lookup of elevation, horizon or snow is made.
    """
    name: str
    latitude: float
    longitude: float
    altitude_m: float
    horizon_degrees: tuple[float, ...]
    uv_albedo: float

    def __post_init__(self):
        values = [self.latitude, self.longitude, self.altitude_m, self.uv_albedo]
        if not self.name or not np.all(np.isfinite(values)):
            raise ValueError("POI needs a name and finite local values")
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("Invalid POI position")
        if not -100 <= self.altitude_m <= 5000 or not 0 <= self.uv_albedo <= .85:
            raise ValueError("POI altitude/albedo outside supported domain")
        h = np.asarray(self.horizon_degrees, float)
        if h.ndim != 1 or len(h) < 4 or not np.all(np.isfinite(h)) or np.any((h < 0) | (h > 90)):
            raise ValueError("Provide >=4 finite horizon elevations 0..90, equally spaced from north")


def _xyz(lat, lon):
    a, b = np.deg2rad(lat), np.deg2rad(lon)
    return np.column_stack([np.cos(a)*np.cos(b), np.cos(a)*np.sin(b), np.sin(a)])


def compute_pois(grid, pois, table=None, *, maximum_distance_km=10):
    """Recompute at caller-supplied POIs using retained grid atmospheric state.

    Pressure is hydrostatically adjusted with fixed 8434 m scale height. Ozone,
    AOD and inferred cloud are retained from the nearest cell, explicitly flagged.
    Terrain output is a screening proxy: isotropic sky, no terrain reflections.
    """
    if member_ids(grid) is not None:
        return map_members(compute_pois, grid, pois=list(pois), table=table,
                           maximum_distance_km=maximum_distance_km)
    table = RadiationTable() if table is None else table
    if grid.attrs.get("radiation_table_sha256") != table.sha256:
        raise ValueError("POI radiation table differs from grid; recompute grid with this table")
    pois = list(pois)
    if not pois or len({p.name for p in pois}) != len(pois):
        raise ValueError("Supply nonempty, uniquely named POIs")
    if maximum_distance_km <= 0:
        raise ValueError("Maximum distance must be positive")
    if "bbox" in grid.attrs:
        west, south, east, north = json.loads(grid.attrs["bbox"])
        if any(not (west <= p.longitude <= east and south <= p.latitude <= north) for p in pois):
            raise ValueError("POI outside declared grid subdomain")
    tree = cKDTree(_xyz(grid.latitude.values, grid.longitude.values))
    distances, cells = tree.query(_xyz([p.latitude for p in pois], [p.longitude for p in pois]))
    distances = 2*6371*np.arcsin(np.minimum(distances/2, 1))
    if np.any(distances > maximum_distance_km):
        raise ValueError("POI too far from available ICON cells")
    samples = int(grid.attrs["solar_samples_per_hour"])
    shape = (grid.sizes["time"], len(pois))
    variables = {k: np.full(shape, np.nan) for k in ("uvi", "clear_sky_uvi", "terrain_screened_uvi",
                  "erythemal_direct", "erythemal_diffuse", "pressure_pa")}
    flags = grid.quality_flag.values[:, cells].astype(np.uint16) | 16 | 32
    for j, (poi, cell) in enumerate(zip(pois, cells)):
        local = grid.isel(cell=int(cell))
        pressure = local.pressure_pa.values*np.exp(-(poi.altitude_m-float(local.altitude_m))/8434)
        horizon = np.asarray(poi.horizon_degrees)
        sky = np.mean(np.cos(np.deg2rad(horizon))**2)
        azimuth = np.linspace(0, 360, len(horizon)+1)
        for i, bounds in enumerate(grid.time_bounds.values):
            if not all(np.isfinite(local[k].values[i]) for k in
                       ('ozone_du', 'pressure_pa', 'aod550', 'effective_cloud_tau550', 'cloud_scale')):
                flags[i, j] |= 128
                continue
            z, az, distance = solar_geometry(_sample_times(bounds, samples), poi.latitude, poi.longitude)
            if np.any((z > 78) & (z < 90)):
                flags[i, j] |= 64
            args = (z, float(local.ozone_du[i]), pressure[i], float(local.aod550[i]), poi.uv_albedo)
            components = table.at(*args, float(local.effective_cloud_tau550[i]))[..., 2:]
            components *= distance[:, None]*float(local.cloud_scale[i])
            clear = table.at(*args, 0)[..., 2:]*distance[:, None]
            h = np.interp(az, azimuth, np.r_[horizon, horizon[0]])
            screened = components[:, 0]*(90-z > h)+components[:, 1]*sky
            variables["uvi"][i, j] = 40*components.sum(axis=-1).mean()
            variables["clear_sky_uvi"][i, j] = 40*clear.sum(axis=-1).mean()
            variables["terrain_screened_uvi"][i, j] = 40*screened.mean()
            variables["erythemal_direct"][i, j] = components[:, 0].mean()
            variables["erythemal_diffuse"][i, j] = components[:, 1].mean()
            variables["pressure_pa"][i, j] = pressure[i]
    result = xr.Dataset({k: (("time", "poi"), v) for k, v in variables.items()},
                         coords={"time": grid.time, "poi": [p.name for p in pois]})
    result["time_bounds"] = grid.time_bounds
    result["quality_flag"] = (("time", "poi"), flags)
    result.quality_flag.attrs = grid.quality_flag.attrs.copy()
    for name in ("latitude", "longitude", "altitude_m", "uv_albedo"):
        result[name] = ("poi", [getattr(p, name) for p in pois])
    result["source_cell"] = ("poi", grid.cell.values[cells])
    result["source_altitude_m"] = ("poi", grid.altitude_m.values[cells])
    result["source_distance_km"] = ("poi", distances)
    result["horizon_json"] = ("poi", [json.dumps(list(p.horizon_degrees)) for p in pois])
    for name, units in (("latitude", "degrees_north"), ("longitude", "degrees_east"),
                         ("altitude_m", "m"), ("source_altitude_m", "m"),
                         ("uv_albedo", "1"), ("source_distance_km", "km")):
        result[name].attrs["units"] = units
    for name in variables:
        result[name].attrs = {"units": "W m-2" if name.startswith("erythemal") else "Pa" if name == "pressure_pa" else "1",
                              "cell_methods": "time: mean"}
    result.attrs = {k: v for k, v in grid.attrs.items() if k not in ("icon_sources", "compute_seconds")}
    result.attrs.update({"title": "Caller-defined POI UV diagnostic",
                         "geometry": "ambient horizontal plus separate terrain-screening proxy",
                         "local_limitations": "fixed-scale pressure adjustment; unchanged ozone/AOD/cloud column; no above-cloud inference; no anisotropic diffuse or terrain reflection"})
    return result


def compare_observations(forecast, observations):
    """Independent hourly means, exact time/POI matching; no calibration.

    Observation Dataset: uvi(time,poi), qc_good(time,poi), units 1. Caller owns
    calibration/QC and interval matching; missing or unqualified data are excluded.
    """
    for label, ds in (("Forecast", forecast), ("Observations", observations)):
        if "uvi" not in ds or ds.uvi.dims != ("time", "poi"):
            raise ValueError(f"{label} requires uvi(time,poi)")
        if ds.uvi.attrs.get("units") != "1":
            raise ValueError(f"{label} must be UVI in units 1, not unweighted UV or dose")
        for dim in ("time", "poi"):
            if (dim not in ds.coords or ds[dim].dims != (dim,)
                or bool(ds[dim].isnull().any()) or not ds[dim].to_index().is_unique):
                raise ValueError(f"{label} requires named, unique, nonmissing {dim} coordinates")
        if ("time_bounds" not in ds or ds.time_bounds.dims != ("time", "bounds")
            or ds.sizes["bounds"] != 2 or ds.time_bounds.dtype.kind != "M"
            or ds.time.dtype.kind != "M"):
            raise ValueError(f"{label} requires datetime time and time_bounds(time,bounds) with two endpoints")
        bounds = ds.time_bounds.values
        if (np.any(np.isnat(bounds))
            or np.any(bounds[:, 1]-bounds[:, 0] != np.timedelta64(1, "h"))
            or np.any(ds.time.values != bounds[:, 0]+np.timedelta64(30, "m"))):
            raise ValueError(f"{label} bounds must be hourly with time at the midpoint")
    if ("qc_good" not in observations or observations.qc_good.dims != ("time", "poi")
        or observations.qc_good.dtype.kind != "b"):
        raise ValueError("qc_good must be boolean with dimensions time,poi")
    f, o = xr.align(forecast[["uvi", "time_bounds"]],
                    observations[["uvi", "time_bounds", "qc_good"]],
                    join="inner", exclude={"bounds"})
    if not f.sizes.get("time") or not f.sizes.get("poi"):
        raise ValueError("No matched forecast/observation samples")
    if "time_bounds" not in o or not np.array_equal(f.time_bounds, o.time_bounds):
        raise ValueError("Observation interval bounds must match forecast")
    mask = np.isfinite(f.uvi) & np.isfinite(o.uvi) & o.qc_good
    error = (f.uvi-o.uvi).where(mask)
    n = int(mask.sum())
    if not n:
        raise ValueError("No valid QC-passed comparison samples")
    return {"samples": n, "bias_uvi": float(error.mean()),
            "mae_uvi": float(abs(error).mean()), "rmse_uvi": float(np.sqrt((error**2).mean())),
            "warning": "Matched-sample statistics only; inspect seasons, elevation and weather regimes separately"}
