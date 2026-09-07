"""Gridded numerical products and caller-owned POI geometry. No HTTP server."""
from dataclasses import dataclass
import json
import time

import numpy as np
from scipy.interpolate import RegularGridInterpolator
import xarray as xr

from . import __version__
from .ensemble import member_ids, map_members
from .data import utc, _validate_cams
from .radiation import FLAG_MEANINGS, RadiationTable, solar_geometry
from .state import validate_grid, positive_distance, SOLAR_SAMPLES
from .locations import PointLocation, load_locations, plan_support, prepare_point
from .evaluation import evaluate_uv


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
    cams = _validate_cams(cams)
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
    if (isinstance(chunk_size, (bool, np.bool_)) or not isinstance(chunk_size, (int, np.integer)) or chunk_size < 1
            or isinstance(samples, (bool, np.bool_)) or samples not in SOLAR_SAMPLES):
        raise ValueError("Positive chunk size; samples must be 1,2,4,6,12")
    ids = member_ids(icon)
    first = icon.sel(member=ids[0], drop=True) if ids is not None else icon
    _check_icon(first, allow_missing="minimum_member_fraction" in icon.attrs or "ensemble_members" in icon.attrs)
    table = RadiationTable() if table is None else table
    composition = _cams_on_icon(cams, first)
    kwargs = dict(cams=cams, table=table, composition=composition, chunk_size=chunk_size,
                  samples=samples, progress=progress)
    if ids is not None:
        return map_members(_compute_grid_member, icon, shared_vars=('ozone_du', 'aod550'), **kwargs)
    return _compute_grid_member(icon, **kwargs)


def _compute_grid_member(icon, *, cams, table, composition, chunk_size, samples, progress):
    _check_icon(icon, allow_missing="minimum_member_fraction" in icon.attrs or "ensemble_members" in icon.attrs)
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
        if self.horizon_degrees is None:
            raise ValueError('POI requires explicit horizon elevations')
        PointLocation(self.name, self.latitude, self.longitude, self.altitude_m,
                      treatment='adjusted', uv_albedo=self.uv_albedo, horizon_degrees=self.horizon_degrees)


def _xyz(lat, lon):
    a, b = np.deg2rad(lat), np.deg2rad(lon)
    return np.column_stack([np.cos(a)*np.cos(b), np.cos(a)*np.sin(b), np.sin(a)])


def compute_pois(grid, pois, table=None, *, maximum_distance_km=10):
    """Compatibility API for explicitly adjusted points with mandatory horizons."""
    maximum_distance_km = positive_distance(maximum_distance_km)
    locations = [PointLocation(p.name, p.latitude, p.longitude, p.altitude_m,
                               treatment='adjusted', uv_albedo=p.uv_albedo,
                               horizon_degrees=p.horizon_degrees,
                               maximum_distance_km=maximum_distance_km) for p in pois]
    return compute_points(grid, locations, table)


def compute_points(grid, locations, table=None):
    """Hourly native or adjusted point forecasts from the shared location model.

    Native points retain source-cell geometry and surface. Adjusted points use
    local elevation and inherit model UV albedo unless explicitly overridden;
    terrain UV requires an explicit horizon.
    The member axis is retained without averaging atmospheric inputs.
    """
    catalog = load_locations(locations)
    if len(catalog.points) != len(catalog.locations):
        raise ValueError('Hourly point forecasts require point locations, not regions')
    table = RadiationTable() if table is None else table
    if grid.attrs.get('radiation_table_sha256') != table.sha256:
        raise ValueError('POI radiation table differs from grid; recompute grid with this table')
    ids = member_ids(grid)
    for m in ids or [None]:
        validate_grid(grid.sel(member=m, drop=True) if m is not None else grid, table, require_samples=True)
    plans = [plan_support(grid, p) for p in catalog.points]
    if any(len(p.indices) != 1 for p in plans):
        raise ValueError('POI too far from suitable ICON cells or outside declared grid subdomain')
    if ids is not None:
        return map_members(_compute_points_member, grid, plans=plans, table=table)
    return _compute_points_member(grid, plans=plans, table=table)


def _compute_points_member(grid, *, plans, table):
    samples = int(grid.attrs['solar_samples_per_hour'])
    shape = (grid.sizes['time'], len(plans))
    names = ('uvi', 'clear_sky_uvi', 'terrain_screened_uvi', 'erythemal_direct', 'erythemal_diffuse', 'pressure_pa')
    variables = {k: np.full(shape, np.nan) for k in names}
    flags = np.zeros(shape, dtype=np.uint16)
    albedo = np.full(shape, np.nan)
    for j, plan in enumerate(plans):
        local = prepare_point(grid, plan)
        point = plan.location
        albedo[:, j] = local.uv_albedo.values[:, 0]
        for i, bounds in enumerate(grid.time_bounds.values):
            times = _sample_times(bounds, samples)
            state = local.isel(time=i)
            components, screened, valid, flag = evaluate_uv(state, times, table, horizon_degrees=point.horizon_degrees)
            clear, _, _, _ = evaluate_uv(state, times, table, clear_sky=True)
            flags[i, j] = flag[0]
            if not valid[0]:
                continue
            mean = components[:, 0].mean(axis=0)
            variables['uvi'][i, j] = 40*mean.sum()
            variables['clear_sky_uvi'][i, j] = 40*clear[:, 0].sum(axis=-1).mean()
            if point.horizon_degrees is not None:
                variables['terrain_screened_uvi'][i, j] = screened[:, 0].mean()
            variables['erythemal_direct'][i, j] = mean[0]
            variables['erythemal_diffuse'][i, j] = mean[1]
            variables['pressure_pa'][i, j] = float(state.pressure_pa.values[0])
    points = [p.location for p in plans]
    cells = np.array([p.indices[0] for p in plans])
    result = xr.Dataset({k: (('time', 'poi'), v) for k, v in variables.items()},
                        coords={'time': grid.time, 'poi': [p.id for p in points]})
    result['time_bounds'] = grid.time_bounds
    result['quality_flag'] = (('time', 'poi'), flags)
    result.quality_flag.attrs = grid.quality_flag.attrs.copy()
    for name in ('latitude', 'longitude', 'altitude_m'):
        result[name] = ('poi', [getattr(p, name) for p in points])
    if all(p.uv_albedo is not None for p in points):
        result['uv_albedo'] = ('poi', [p.uv_albedo for p in points])
    else:
        result['uv_albedo'] = (('time', 'poi'), albedo)
    result['treatment'] = ('poi', [p.treatment for p in points])
    result['source_cell'] = ('poi', grid.cell.values[cells])
    result['source_altitude_m'] = ('poi', grid.altitude_m.values[cells])
    result['source_latitude'] = ('poi', grid.latitude.values[cells])
    result['source_longitude'] = ('poi', grid.longitude.values[cells])
    result['source_distance_km'] = ('poi', [p.distances_km[0] for p in plans])
    result['horizon_json'] = ('poi', [json.dumps(p.horizon_degrees) for p in points])
    for name, units in (('latitude', 'degrees_north'), ('longitude', 'degrees_east'),
                        ('altitude_m', 'm'), ('source_altitude_m', 'm'), ('source_latitude', 'degrees_north'), ('source_longitude', 'degrees_east'), ('uv_albedo', '1'), ('source_distance_km', 'km')):
        result[name].attrs['units'] = units
    for name in variables:
        result[name].attrs = {'units': 'W m-2' if name.startswith('erythemal') else 'Pa' if name == 'pressure_pa' else '1', 'cell_methods': 'time: mean'}
    result.terrain_screened_uvi.attrs['comment'] = 'NaN without explicit horizon geometry'
    result.attrs = {k: v for k, v in grid.attrs.items() if k not in ('icon_sources', 'compute_seconds')}
    result.attrs.update(title='Location UV diagnostic', geometry='explicit native or adjusted point treatment',
                        local_limitations='fixed-scale pressure adjustment; unchanged ozone/AOD/cloud column; no above-cloud inference; no anisotropic diffuse or terrain reflection')
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
