"""Daily map-data contract: explicit temporal/spatial support and failure states."""
from datetime import date, datetime, time, timedelta, timezone
from dataclasses import dataclass
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import numpy as np

from .radiation import RadiationTable, solar_geometry
from .state import validate_grid
from .data import utc
from .evaluation import evaluate_uv
from .locations import (load_locations, location_from_entry, plan_support, prepare_point,
                        PointLocation, RegionBand, REGION_MINIMUM_CELLS, REGION_MINIMUM_FRACTION, REGION_QUANTILE)
from .ensemble import member_ids, ensemble_metadata, summary, required_members, quantile_available

CONTRACT_VERSION = 'daily-uv-v1'
CONTRACT_SHA256 = 'aabfc3713c5664d365b5336cebfaa65d119a834a227b0f0542b4b94fc0e9bd36'
FORECAST_CONTRACT_VERSION = 'daily-uv-v2'
FORECAST_CONTRACT_SHA256 = hashlib.sha256(
    b'daily-uv-v2: v1 support and peaks; all forecast daylight dates; explicit valid_dates'
).hexdigest()
ENSEMBLE_CONTRACT_VERSION = 'daily-uv-v3'
ENSEMBLE_CONTRACT_SHA256 = hashlib.sha256(b'daily-uv-v3: memberwise daily/spatial products, then ensemble quantile; uncalibrated uncertainty').hexdigest()
LOCATION_CONTRACT_VERSION = 'daily-uv-v5'
LOCATION_CONTRACT_SHA256 = hashlib.sha256(
    b'daily-uv-v5: adjusted points default to inherited model UV albedo; optional explicit horizon; ambient horizontal UV'
).hexdigest()
CATEGORIES = ('low', 'moderate', 'high', 'very_high', 'extreme')
PEAK_DEFINITION = 'maximum_30min_mean_on_5min_grid_hourly_cloud_reconstruction'


def display_value(value):
    """Round nonnegative finite UVI, with explicit upward half-integer ties."""
    value = float(value)
    if not np.isfinite(value) or value < 0:
        raise ValueError('UVI must be finite and nonnegative')
    number = int(np.floor(value + .5))
    index = int(np.searchsorted([3, 6, 8, 11], number, side='right'))
    return number, CATEGORIES[index]


def utc_instant(value):
    try:
        return utc(value)
    except ValueError as exc:
        raise ValueError(f'Invalid timezone-aware instant: {exc}') from exc


def local_day_bounds(value):
    day = date.fromisoformat(str(value))
    zone = ZoneInfo('Europe/Zurich')
    ends = [datetime.combine(day + timedelta(days=d), time(), zone) for d in (0, 1)]
    return tuple(np.datetime64(t.astimezone(timezone.utc).replace(tzinfo=None), 'ns') for t in ends)


def daylight_hours(value, latitude, longitude):
    """Full UTC hours containing any sun-above-horizon one-minute midpoint."""
    start, end = local_day_bounds(value)
    hours = np.arange(start, end, np.timedelta64(1, 'h'))
    minute = hours[:, None] + np.arange(60)[None, :] * np.timedelta64(1, 'm') + np.timedelta64(30, 's')
    z, _, _ = solar_geometry(minute[:, :, None], np.asarray(latitude)[None, None, :],
                             np.asarray(longitude)[None, None, :])
    return hours, np.any(z < 90, axis=1)


_check_grid = validate_grid


def daily_cells(grid, valid_date, table=None, chunk_size=256, *, clear_sky=False, ensemble_quantile=.5,
                horizon_degrees=None, terrain_screened=False):
    """Reconstruct native-cell peaks; gaps in daylight never become partial maxima.

    Returns arrays in source-cell order, with NaN only for unavailable values.
    Output JSON conversion occurs at the export boundary. With clear_sky=True,
    remove cloud optical depth and cloud scaling, retaining atmosphere/surface
    and the same full-day coverage requirements.
    """
    ids = member_ids(grid)
    ensemble_metadata(ids or [], ensemble_quantile)
    table = RadiationTable() if table is None else table
    if ids is not None:
        members = [daily_cells(grid.sel(member=m, drop=True), valid_date, table, chunk_size,
                               clear_sky=clear_sky, horizon_degrees=horizon_degrees,
                               terrain_screened=terrain_screened) for m in ids]
        values = np.stack([r['uvi'] for r in members])
        hourly = np.stack([r['hourly_max_uvi'] for r in members])
        peaks = np.stack([r['peak_start'] for r in members])
        _, _, minimum = required_members(grid)
        count = np.isfinite(values).sum(axis=0)
        available = count >= minimum
        peak_range = _peak_range(peaks, np.isfinite(values))
        peak_range[~available] = np.datetime64('NaT')
        return dict(uvi=np.where(available, quantile_available(values, ensemble_quantile, axis=0), np.nan),
                    hourly_max_uvi=np.where(available, quantile_available(hourly, ensemble_quantile, axis=0), np.nan),
                    available=available, member_count=count,
                    quality_flag=np.bitwise_or.reduce([r['quality_flag'] for r in members], axis=0),
                    peak_start=peak_range[:, 0], peak_start_range=peak_range,
                    member_peak_start=peaks, member_uvi=values,
                    member_quality_flag=np.stack([r['quality_flag'] for r in members]))
    bounds = _check_grid(grid, table)
    if isinstance(chunk_size, (bool, np.bool_)) or not isinstance(chunk_size, (int, np.integer)) or chunk_size < 1:
        raise ValueError('Positive chunk size required')
    start, end = local_day_bounds(valid_date)
    bin_starts = np.arange(start, end, np.timedelta64(5, 'm'))
    n = grid.sizes['cell']
    result = {k: np.full(n, np.nan) for k in ('uvi', 'hourly_max_uvi')}
    result['peak_start'] = np.full(n, np.datetime64('NaT'), dtype='datetime64[ns]')
    result['available'] = np.zeros(n, dtype=bool)
    result['quality_flag'] = np.zeros(n, dtype=np.uint16)
    lookup = {t: i for i, t in enumerate(bounds[:, 0])}
    for offset in range(0, n, chunk_size):
        sl = slice(offset, min(offset+chunk_size, n))
        local = grid.isel(cell=sl)
        hours, required = daylight_hours(valid_date, local.latitude.values, local.longitude.values)
        complete = np.ones(local.sizes['cell'], dtype=bool)
        samples = np.zeros((len(bin_starts), local.sizes['cell']))
        flags = np.zeros(local.sizes['cell'], dtype=np.uint16)
        for h, hour in enumerate(hours):
            i = lookup.get(hour)
            if i is None:
                complete &= ~required[h]
                continue
            t = hour + np.arange(12)*np.timedelta64(5, 'm') + np.timedelta64(150, 's')
            components, screened, valid, sample_flags = evaluate_uv(
                local.isel(time=i), t, table, clear_sky=clear_sky, horizon_degrees=horizon_degrees)
            complete &= valid | ~required[h]
            values = screened if terrain_screened else 40*components.sum(axis=-1)
            values = np.where(valid[None, :], values, 0.)
            if not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError('Invalid reconstructed UVI')
            samples[h*12:(h+1)*12] = values
            flags |= sample_flags
        windows = np.lib.stride_tricks.sliding_window_view(samples, 6, axis=0).mean(axis=-1)
        peaks = windows.argmax(axis=0)
        result['uvi'][sl] = np.where(complete, windows[peaks, np.arange(len(peaks))], np.nan)
        result['hourly_max_uvi'][sl] = np.where(complete, samples.reshape(-1, 12, len(peaks)).mean(axis=1).max(axis=0), np.nan)
        result['peak_start'][sl] = np.where(complete, bin_starts[peaks], np.datetime64('NaT'))
        result['available'][sl] = complete
        result['quality_flag'][sl] = flags
    return result


def _peak_range(peaks, valid):
    """Earliest/latest contributing member windows, ignoring unavailable NaT."""
    integers = peaks.astype('datetime64[ns]').astype('int64')
    valid = valid & ~np.isnat(peaks)
    earliest = np.where(valid, integers, np.iinfo('int64').max).min(axis=0)
    latest = np.where(valid, integers, np.iinfo('int64').min).max(axis=0)
    result = np.stack([earliest, latest], axis=-1).astype('datetime64[ns]')
    result[~valid.any(axis=0)] = np.datetime64('NaT')
    return result


def select_support(grid, entry):
    """Compatibility adapter for native catalog selection."""
    return plan_support(grid, location_from_entry(entry)).indices


def forecast_dates(grid, first):
    """Dates from issuance through the last supplied daylight interval.

    A trailing night-only local date is excluded. Gaps and partial daylight days
    remain visible and are assessed by daily_cells, never scored as full peaks.
    """
    bounds = grid.time_bounds.values.astype('datetime64[ns]')
    if not len(bounds) or not grid.sizes['cell']:
        raise ValueError('Forecast dates require nonempty time and cell dimensions')
    last = utc_instant(str(bounds[-1, 1] - np.timedelta64(1, 's')) + 'Z')
    last = last.astimezone(ZoneInfo('Europe/Zurich')).date()
    # Corners bound the geographic domain without allocating a full-grid solar array.
    lat = grid.latitude.values; lon = grid.longitude.values
    latitudes = [lat.min(), lat.min(), lat.max(), lat.max()]
    longitudes = [lon.min(), lon.max(), lon.min(), lon.max()]
    while last >= first:
        hours, required = daylight_hours(str(last), latitudes, longitudes)
        if np.any(required & np.isin(hours, bounds[:, 0])[:, None]):
            return [str(first + timedelta(days=d)) for d in range((last-first).days+1)]
        last -= timedelta(days=1)
    raise ValueError('No forecast daylight at or after issuance date')


@dataclass
class DailyResult:
    """Calculated location products before issuance/freshness and file encoding."""
    entries: list[dict]
    valid_dates: list[str]
    catalog: dict
    source_attrs: dict
    radiation_table_sha256: str
    ensemble: dict | None
    uv_geometry: str = 'ambient_horizontal'


def _dates(values):
    if isinstance(values, (str, date)):
        values = [values]
    dates = [date.fromisoformat(str(v)).isoformat() for v in values]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('Provide nonempty, unique, increasing valid dates')
    return dates


def valid_dates(grid, issued_at, *, days=2, dates=None):
    """Resolve explicit dates or a positive count from Swiss-local issuance."""
    first = utc_instant(issued_at).astimezone(ZoneInfo('Europe/Zurich')).date()
    if dates is not None:
        result = _dates(dates)
        if date.fromisoformat(result[0]) < first:
            raise ValueError('Valid dates cannot precede the local issuance date')
        return result
    if days == 'all':
        return forecast_dates(grid, first)
    if isinstance(days, bool) or not isinstance(days, (int, np.integer)) or days < 1:
        raise ValueError("days must be a positive integer or 'all'")
    return [str(first+timedelta(days=d)) for d in range(days)]


def _validate_source_grid(grid, table):
    ids = member_ids(grid)
    for m in ids or [None]:
        validate_grid(grid.sel(member=m, drop=True) if m is not None else grid, table)
    icon_start = np.datetime64(utc_instant(grid.attrs['forecast_reference_time']).replace(tzinfo=None), 'ns')
    if np.any(grid.time_bounds.values[:, 0] < icon_start):
        raise ValueError('Forecast intervals precede the ICON cycle')
    return ids


def _location_row(entry, plan, source, daily, indices, minimum, expected, ensemble):
    """Spatial validity and aggregation precede member coverage and reduction."""
    region = isinstance(plan.location, RegionBand)
    required_cells = REGION_MINIMUM_CELLS if region else 1
    required_fraction = REGION_MINIMUM_FRACTION if region else 1.
    row = dict(location=entry, status='unavailable', reasons=[], selected_cells=len(indices),
               valid_cells=0, uvi=None, display_uvi=None, category=None)
    if len(indices) < required_cells:
        row['reasons'].append('insufficient_native_support')
        return row
    if ensemble is None:
        values = np.where(daily['available'][indices], daily['uvi'][indices], np.nan)[None, :]
        peaks = daily['peak_start'][indices][None, :]
        flags = daily['quality_flag'][indices][None, :]
    else:
        values = daily['member_uvi'][:, indices]
        peaks = daily['member_peak_start'][:, indices]
        flags = daily['member_quality_flag'][:, indices]
    finite = np.isfinite(values)
    counts = finite.sum(axis=1)
    eligible = (counts >= required_cells) & (counts/len(indices) >= required_fraction)
    contributions = finite & eligible[:, None]
    good = contributions.any(axis=0)
    row['valid_cells'] = int(good.sum())
    if eligible.sum() < minimum:
        row['reasons'].append('incomplete_daylight')
        if ensemble is not None:
            row['reasons'].append('insufficient_ensemble_members')
        return row
    member_values = np.full(len(values), np.nan)
    for m in np.flatnonzero(eligible):
        member_values[m] = np.quantile(values[m, finite[m]], REGION_QUANTILE) if region else values[m, 0]
    value = float(quantile_available(member_values, ensemble['deterministic_quantile'])) if ensemble is not None else float(member_values[0])
    number, category = display_value(value)
    contributing_values = values[contributions]
    contributing_peaks = peaks[contributions]
    point = plan.location if not region else None
    adjusted = point is not None and point.treatment == 'adjusted'
    row.update(uvi=value, display_uvi=number, category=category, status='ok',
               aggregation='p90_of_native_cell_daily_maxima' if region else 'adjusted_point_daily_maximum' if adjusted else 'nearest_suitable_native_cell',
               support_uvi_range=[float(contributing_values.min()), float(contributing_values.max())],
               support_uvi_median=float(np.median(contributing_values)),
               source_cells=[int(v) for v in source.cell.values[plan.indices][good]],
               peak_window_start_range_utc=[str(contributing_peaks.min())+'Z', str(contributing_peaks.max())+'Z'],
               quality_flag=int(np.bitwise_or.reduce(flags[contributions])))
    if np.any(counts[eligible] < len(indices)):
        row['reasons'].append('partial_spatial_support')
    if ensemble is not None:
        row['ensemble'] = summary(member_values)
        row['ensemble']['member_valid_cells'] = np.where(eligible, counts, 0).tolist()
        if eligible.sum() < len(expected):
            row['reasons'].append('partial_ensemble_support')
    if row['reasons']:
        row['status'] = 'degraded'
    if point is not None:
        cell = int(plan.indices[0])
        row['source_point'] = {k: float(source[k].values[cell]) for k in ('latitude', 'longitude', 'altitude_m')}
        row['source_point'].update(cell=int(source.cell.values[cell]),
                                   altitude_difference_m=float(source.altitude_m.values[cell])-point.altitude_m)
        if ensemble is None:
            row['peak_window_start_utc'] = str(contributing_peaks[0])+'Z'
    return row


def compute_daily(grid, locations, dates, table=None, *, ensemble_quantile=.5, terrain_screened=False):
    """Daily rolling peaks from native or explicitly adjusted location state.

    Pure calculation: dates are explicit; no file hash or issuance is needed.
    Regions aggregate each member's native peaks before ensemble reduction.
    """
    table = RadiationTable() if table is None else table
    ids = _validate_source_grid(grid, table)
    expected, fraction, minimum = required_members(grid)
    metadata = ensemble_metadata(ids or [], ensemble_quantile, expected=expected, fraction=fraction)
    ensemble = metadata if ids is not None else None
    catalog = load_locations(locations)
    dates = _dates(dates)
    plans = [plan_support(grid, p) for p in catalog.locations]
    if terrain_screened and any(not isinstance(p, PointLocation) or p.horizon_degrees is None for p in catalog.locations):
        raise ValueError('Terrain screening requires an explicit horizon for every location; regions and native points use ambient UV')
    native = [p.indices for p in plans if not (isinstance(p.location, PointLocation) and p.location.treatment == 'adjusted')]
    union = np.unique(np.concatenate(native)) if native else np.array([], dtype=int)
    selected = grid.isel(cell=union)
    by_index = {int(cell): i for i, cell in enumerate(union)}
    adjusted = {i: prepare_point(grid, p) for i, p in enumerate(plans)
                if isinstance(p.location, PointLocation) and p.location.treatment == 'adjusted' and len(p.indices)}
    rows = []
    for day, valid in enumerate(dates):
        # Keep the deterministic call signature compatible with simple callers.
        daily = (daily_cells(selected, valid, table, ensemble_quantile=ensemble_quantile) if ids is not None
                 else daily_cells(selected, valid, table)) if len(union) else None
        for i, (entry, plan) in enumerate(zip(catalog.catalog['entries'], plans)):
            if i in adjusted:
                values = daily_cells(adjusted[i], valid, table, ensemble_quantile=ensemble_quantile,
                                     horizon_degrees=plan.location.horizon_degrees, terrain_screened=terrain_screened)
                indices = np.array([0])
            else:
                values = daily
                indices = np.array([by_index[int(v)] for v in plan.indices], dtype=int)
            row = _location_row(entry, plan, grid, values, indices, minimum if ids is not None else 1, expected, ensemble)
            row.update(valid_date=valid, day=day)
            rows.append(row)
    return DailyResult(rows, dates, catalog.catalog, dict(grid.attrs), table.sha256, ensemble,
                       'terrain_screened' if terrain_screened else 'ambient_horizontal')


def _sources(attrs, issue):
    sources, reasons = {}, []
    for label, key, limit in [('icon', 'forecast_reference_time', 24), ('cams', 'cams_reference_time', 48)]:
        reference = utc_instant(attrs[key])
        age = (issue-reference).total_seconds()/3600
        if age < 0:
            raise ValueError('Source cycle is later than issuance')
        sources[label] = dict(reference_time=reference.isoformat(), age_hours=age)
        if age > limit:
            reasons.append('stale_'+label)
    return sources, reasons


def daily_payload(result, issued_at, *, input_sha256, schema_version=LOCATION_CONTRACT_VERSION):
    """Apply publication freshness, provenance and schema policy to calculated rows."""
    if not isinstance(input_sha256, str) or len(input_sha256) != 64 or any(c not in '0123456789abcdef' for c in input_sha256):
        raise ValueError('Source file SHA-256 is required')
    hashes = {CONTRACT_VERSION: CONTRACT_SHA256, FORECAST_CONTRACT_VERSION: FORECAST_CONTRACT_SHA256,
              ENSEMBLE_CONTRACT_VERSION: ENSEMBLE_CONTRACT_SHA256,
              'daily-uv-v4': hashlib.sha256(b'daily-uv-v4: explicit location treatment; memberwise spatial support; arbitrary dates; ambient or terrain-screened UV').hexdigest(),
              LOCATION_CONTRACT_VERSION: LOCATION_CONTRACT_SHA256}
    if schema_version not in hashes:
        raise ValueError('Unsupported daily schema version')
    shared = schema_version in ('daily-uv-v4', LOCATION_CONTRACT_VERSION)
    if not shared and any(e['location'].get('kind') not in ('town', 'region_altitude') for e in result.entries):
        raise ValueError('Shared point locations require schema v4 or v5')
    if schema_version == 'daily-uv-v4' and any(
        e['location'].get('treatment') == 'adjusted' and e['location'].get('uv_albedo') is None
        for e in result.entries
    ):
        raise ValueError('Inherited point UV albedo requires schema v5')
    if schema_version == ENSEMBLE_CONTRACT_VERSION and result.ensemble is None:
        raise ValueError('Schema v3 requires ensemble data')
    if schema_version in (CONTRACT_VERSION, FORECAST_CONTRACT_VERSION) and result.ensemble is not None:
        raise ValueError('Ensemble data require schema v3 or later')
    if result.uv_geometry != 'ambient_horizontal' and not shared:
        raise ValueError('Terrain-screened daily output requires schema v4 or v5')
    issue = utc_instant(issued_at)
    first = issue.astimezone(ZoneInfo('Europe/Zurich')).date()
    if date.fromisoformat(result.valid_dates[0]) < first:
        raise ValueError('Valid dates cannot precede the local issuance date')
    if schema_version == CONTRACT_VERSION and result.valid_dates != [str(first), str(first+timedelta(days=1))]:
        raise ValueError('Schema v1 requires issuance date and following day')
    sources, stale = _sources(result.source_attrs, issue)
    rows = deepcopy(result.entries)
    for row in rows:
        row['day'] = (date.fromisoformat(row['valid_date'])-first).days
        if not shared:
            for name in ('uvi_range', 'uvi_median'):
                if 'support_'+name in row:
                    row['native_'+name] = row.pop('support_'+name)
        if stale:
            # Withhold all derived quantities consistently while retaining geometry.
            keep = ('location', 'valid_date', 'day', 'selected_cells')
            preserved = {k: row[k] for k in keep}
            reasons = list(stale)
            if 'insufficient_native_support' in row['reasons']:
                reasons.append('insufficient_native_support')
            row.clear()
            row.update(preserved, status='unavailable', reasons=reasons, valid_cells=0,
                       uvi=None, display_uvi=None, category=None)
    payload = dict(schema_version=schema_version, contract_sha256=hashes[schema_version],
                   issued_at=issue.isoformat(), timezone='Europe/Zurich', peak_definition=PEAK_DEFINITION,
                   category_basis='rounded_integer_half_up',
                   catalog_sha256=hashlib.sha256(json.dumps(result.catalog, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                   input_sha256=input_sha256, radiation_table_sha256=result.radiation_table_sha256, sources=sources,
                   qualification='experimental; site/regime skill must be assessed separately',
                   assumptions=result.source_attrs.get('assumptions', 'source assumptions not supplied'),
                   temporal_limitation='hourly cloud state; solar evolution reconstructed at five-minute midpoints', entries=rows)
    if schema_version != CONTRACT_VERSION:
        payload['valid_dates'] = result.valid_dates
    if result.ensemble is not None:
        payload['ensemble'] = result.ensemble
    if shared:
        payload['uv_geometry'] = result.uv_geometry
    return payload


def write_daily_json(result, path, issued_at, *, input_sha256):
    """Publish calculated shared-location products as schema v5 atomically."""
    payload = daily_payload(result, issued_at, input_sha256=input_sha256)
    write_json_atomic(payload, path)
    return payload


def export_daily(grid, catalog, issued_at, *, input_sha256, table=None, days=2,
                 ensemble_quantile=.5, dates=None, terrain_screened=False):
    """Compatibility publisher; legacy native catalogs retain v1/v2/v3."""
    # Reject issuance errors before expensive reconstruction.
    _sources(grid.attrs, utc_instant(issued_at))
    resolved = valid_dates(grid, issued_at, days=days, dates=dates)
    locations = load_locations(catalog)
    result = compute_daily(grid, locations, resolved, table, ensemble_quantile=ensemble_quantile,
                           terrain_screened=terrain_screened)
    shared = any(e.get('kind') not in ('town', 'region_altitude') for e in locations.catalog['entries'])
    version = (LOCATION_CONTRACT_VERSION if shared or terrain_screened else ENSEMBLE_CONTRACT_VERSION if result.ensemble else
               CONTRACT_VERSION if days == 2 and dates is None else FORECAST_CONTRACT_VERSION)
    return daily_payload(result, issued_at, input_sha256=input_sha256, schema_version=version)


def export_daily_file(grid_path, locations, issued_at, *, output=None, **kwargs):
    """File convenience API: select relevant cells, load, stream hash and publish."""
    import xarray as xr
    from .data import file_sha256
    catalog = load_locations(locations)
    with xr.open_dataset(grid_path) as grid:
        # dates='all' depends on the original domain, including unsupported targets.
        resolved = valid_dates(grid, issued_at, days=kwargs.get('days', 2), dates=kwargs.get('dates'))
        indices = np.unique(np.concatenate([plan_support(grid, p).indices for p in catalog.locations]))
        subset = grid.isel(cell=indices).load()
        if kwargs.get('days') == 'all':
            kwargs = dict(kwargs, dates=resolved)
        payload = export_daily(subset, catalog, issued_at, input_sha256=file_sha256(grid_path), **kwargs)
    if output is not None:
        write_json_atomic(payload, output)
    return payload


def write_json_atomic(payload, path):
    """Never truncate a prior product on serialization or generation failure."""
    content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)+'\n'
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix=path.name+'.', delete=False) as stream:
            temporary = Path(stream.name); stream.write(content); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
