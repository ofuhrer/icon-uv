"""Daily map-data contract: explicit temporal/spatial support and failure states."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import numpy as np

from .radiation import RadiationTable, solar_geometry

CONTRACT_VERSION = 'daily-uv-v1'
CONTRACT_SHA256 = 'aabfc3713c5664d365b5336cebfaa65d119a834a227b0f0542b4b94fc0e9bd36'
FORECAST_CONTRACT_VERSION = 'daily-uv-v2'
FORECAST_CONTRACT_SHA256 = hashlib.sha256(
    b'daily-uv-v2: v1 support and peaks; all forecast daylight dates; explicit valid_dates'
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
    value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Explicit timezone required')
    return value.astimezone(timezone.utc)


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


def _check_grid(grid, table):
    if grid.attrs.get('radiation_table_sha256') != table.sha256:
        raise ValueError('Radiation table differs from source grid')
    for name in ('ozone_du', 'aod550', 'pressure_pa', 'uv_albedo',
                 'effective_cloud_tau550', 'cloud_scale', 'quality_flag'):
        if name not in grid or grid[name].dims != ('time', 'cell'):
            raise ValueError(f'Missing (time,cell) field: {name}')
        if not np.isfinite(grid[name]).all() or np.any(grid[name] < 0):
            raise ValueError(f'Invalid {name}')
        if name != 'quality_flag' and grid[name].attrs.get('units') != ('Pa' if name == 'pressure_pa' else 'DU' if name == 'ozone_du' else '1'):
            raise ValueError(f'Invalid units for {name}')
    if np.any(grid.quality_flag != np.floor(grid.quality_flag)) or np.any(grid.quality_flag > 65535):
        raise ValueError('Invalid quality flag bitmask')
    for name in ('latitude', 'longitude', 'altitude_m'):
        if name not in grid or grid[name].dims != ('cell',) or not np.isfinite(grid[name]).all():
            raise ValueError(f'Invalid {name}')
    if np.any(abs(grid.latitude) > 90) or np.any(abs(grid.longitude) > 180):
        raise ValueError('Invalid geographic coordinates')
    cells = grid.cell.values
    if cells.dtype.kind not in 'iu' or np.any(cells < 0):
        raise ValueError('Native cell identifiers must be nonnegative integers')
    if len(np.unique(cells)) != grid.sizes['cell']:
        raise ValueError('Duplicate native cells')
    bounds = grid.time_bounds.values.astype('datetime64[ns]')
    if bounds.shape != (grid.sizes['time'], 2) or np.isnat(bounds).any():
        raise ValueError('Invalid time bounds')
    if (np.any(bounds[:, 1]-bounds[:, 0] != np.timedelta64(1, 'h')) or
            np.any(bounds[:, 0] != bounds[:, 0].astype('datetime64[h]')) or
            np.any(bounds[1:, 0] < bounds[:-1, 1])):
        raise ValueError('Expected ordered, nonoverlapping UTC hours')
    if np.any(grid.time.values != bounds[:, 0] + np.timedelta64(30, 'm')):
        raise ValueError('Expected interval midpoint time labels')
    return bounds


def daily_cells(grid, valid_date, table=None, chunk_size=256):
    """Reconstruct native-cell peaks; gaps in daylight never become partial maxima.

    Returns arrays in source-cell order, with NaN only for unavailable values.
    Output JSON conversion occurs at the export boundary.
    """
    table = RadiationTable() if table is None else table
    bounds = _check_grid(grid, table)
    if chunk_size < 1:
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
            z, _, distance = solar_geometry(t[:, None], local.latitude.values[None, :],
                                            local.longitude.values[None, :])
            args = [local[k].values[i] for k in ('ozone_du', 'pressure_pa', 'aod550', 'uv_albedo', 'effective_cloud_tau550')]
            components = table.at(z, *args)[..., 2:]
            values = 40*components.sum(axis=-1)*distance*local.cloud_scale.values[i]
            if not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError('Invalid reconstructed UVI')
            samples[h*12:(h+1)*12] = values
            flags |= local.quality_flag.values[i].astype(np.uint16)
            flags |= np.where(np.any((z > 78) & (z < 90), axis=0), 64, 0).astype(np.uint16)
        windows = np.lib.stride_tricks.sliding_window_view(samples, 6, axis=0).mean(axis=-1)
        peaks = windows.argmax(axis=0)
        result['uvi'][sl] = np.where(complete, windows[peaks, np.arange(len(peaks))], np.nan)
        result['hourly_max_uvi'][sl] = np.where(complete, samples.reshape(-1, 12, len(peaks)).mean(axis=1).max(axis=0), np.nan)
        result['peak_start'][sl] = np.where(complete, bin_starts[peaks], np.datetime64('NaT'))
        result['available'][sl] = complete
        result['quality_flag'][sl] = flags
    return result


def select_support(grid, entry):
    """Explicit native support, with no vertical cloud-column transplantation."""
    lat, lon, height = (grid[k].values for k in ('latitude', 'longitude', 'altitude_m'))
    if entry['kind'] == 'town':
        target_lat, target_lon, target_z = (float(entry[k]) for k in ('latitude', 'longitude', 'altitude_m'))
        if not (-90 <= target_lat <= 90 and -180 <= target_lon <= 180) or not np.isfinite(target_z):
            raise ValueError('Invalid town coordinates')
        phi = np.deg2rad(lat); origin = np.deg2rad(target_lat)
        a = np.sin((phi-origin)/2)**2 + np.cos(phi)*np.cos(origin)*np.sin(np.deg2rad(lon-target_lon)/2)**2
        distance = 12742*np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        allowed = np.flatnonzero((distance <= 5) & (abs(height-target_z) <= 300))
        return allowed[np.argsort(distance[allowed], kind='stable')[:1]]
    if entry['kind'] == 'region_altitude':
        w, s, e, n = map(float, entry['bbox'])
        target = float(entry['altitude_m'])
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90) or target not in (1000, 2000, 3000):
            raise ValueError('Invalid region bounds or unsupported altitude')
        return np.flatnonzero((lon >= w) & (lon <= e) & (lat >= s) & (lat <= n) & (abs(height-target) <= 200))
    raise ValueError('Unsupported location kind')


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


def export_daily(grid, catalog, issued_at, *, input_sha256, table=None, days=2):
    """Export two days (v1), or all supplied forecast daylight dates (v2)."""
    if days != 2 and days != 'all':
        raise ValueError("days must be 2 or 'all'")
    issue = utc_instant(issued_at)
    if not isinstance(input_sha256, str) or len(input_sha256) != 64 or any(c not in '0123456789abcdef' for c in input_sha256):
        raise ValueError('Source file SHA-256 is required')
    table = RadiationTable() if table is None else table
    _check_grid(grid, table)
    entries = catalog['entries']
    if not entries or len({e['id'] for e in entries}) != len(entries):
        raise ValueError('Nonempty, unique catalog identifiers required')
    sources = {}
    source_reasons = []
    for label, key, limit in [('icon', 'forecast_reference_time', 24), ('cams', 'cams_reference_time', 48)]:
        reference = utc_instant(grid.attrs[key]); age = (issue-reference).total_seconds()/3600
        sources[label] = {'reference_time': reference.isoformat(), 'age_hours': age}
        if age < 0:
            raise ValueError('Source cycle is later than issuance')
        if age > limit:
            source_reasons.append(f'stale_{label}')
    icon_start = np.datetime64(utc_instant(grid.attrs['forecast_reference_time']).replace(tzinfo=None), 'ns')
    if np.any(grid.time_bounds.values[:, 0] < icon_start):
        raise ValueError('Forecast intervals precede the ICON cycle')
    support = [select_support(grid, e) for e in entries]
    union = np.unique(np.concatenate(support))
    selected = grid.isel(cell=union)
    by_index = {int(cell): i for i, cell in enumerate(union)}
    first = issue.astimezone(ZoneInfo('Europe/Zurich')).date()
    dates = (forecast_dates(grid, first) if days == 'all' else
             [str(first + timedelta(days=d)) for d in (0, 1)])
    rows = []
    for day, valid in enumerate(dates):
        daily = daily_cells(selected, valid, table) if len(union) and not source_reasons else None
        for entry, indices in zip(entries, support):
            local = np.array([by_index[int(i)] for i in indices], dtype=int)
            good = local[daily['available'][local]] if daily is not None else np.array([], dtype=int)
            region = entry['kind'] == 'region_altitude'
            reasons = list(source_reasons)
            if len(indices) < (5 if region else 1):
                reasons.append('insufficient_native_support')
            elif daily is not None and len(good)/len(indices) < (.95 if region else 1):
                reasons.append('incomplete_daylight')
            row = dict(location=entry, valid_date=valid, day=day, status='unavailable', reasons=reasons,
                       selected_cells=len(indices), valid_cells=len(good), uvi=None, display_uvi=None, category=None)
            if not reasons:
                values = daily['uvi'][good]
                value = float(np.quantile(values, .9)) if region else float(values[0])
                integer, category = display_value(value)
                row.update(uvi=value, display_uvi=integer, category=category,
                           status='degraded' if len(good) < len(indices) else 'ok',
                           aggregation='p90_of_native_cell_daily_maxima' if region else 'nearest_suitable_native_cell',
                           native_uvi_range=[float(values.min()), float(values.max())],
                           native_uvi_median=float(np.median(values)),
                           source_cells=[int(selected.cell.values[i]) for i in good],
                           peak_window_start_range_utc=[str(daily['peak_start'][good].min())+'Z', str(daily['peak_start'][good].max())+'Z'],
                           quality_flag=int(np.bitwise_or.reduce(daily['quality_flag'][good])))
                if row['status'] == 'degraded':
                    row['reasons'].append('partial_spatial_support')
                if not region:
                    i = int(good[0])
                    row['source_point'] = {k: float(selected[k].values[i]) for k in ('latitude', 'longitude', 'altitude_m')}
                    row['source_point']['cell'] = int(selected.cell.values[i])
                    row['source_point']['altitude_difference_m'] = row['source_point']['altitude_m']-float(entry['altitude_m'])
                    row['peak_window_start_utc'] = str(daily['peak_start'][i])+'Z'
            rows.append(row)
    payload = dict(schema_version=CONTRACT_VERSION, contract_sha256=CONTRACT_SHA256,
                issued_at=issue.isoformat(), timezone='Europe/Zurich',
                peak_definition=PEAK_DEFINITION, category_basis='rounded_integer_half_up',
                catalog_sha256=hashlib.sha256(json.dumps(catalog, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                input_sha256=input_sha256, radiation_table_sha256=table.sha256,
                sources=sources, qualification='experimental; site/regime skill must be assessed separately',
                assumptions=grid.attrs.get('assumptions', 'source assumptions not supplied'),
                temporal_limitation='hourly cloud state; solar evolution reconstructed at five-minute midpoints',
                entries=rows)
    if days == 'all':
        payload.update(schema_version=FORECAST_CONTRACT_VERSION,
                       contract_sha256=FORECAST_CONTRACT_SHA256, valid_dates=dates)
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
