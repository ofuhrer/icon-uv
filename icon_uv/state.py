"""Shared contract for the saved atmospheric state used to reconstruct UV."""
from numbers import Real

import numpy as np


SOLAR_SAMPLES = (1, 2, 4, 6, 12)
STATE_UNITS = {
    'ozone_du': 'DU', 'aod550': '1', 'pressure_pa': 'Pa',
    'uv_albedo': '1', 'effective_cloud_tau550': '1', 'cloud_scale': '1',
}


def positive_distance(value):
    """Return a finite positive distance, rejecting booleans and malformed values."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value) or value <= 0:
        raise ValueError('maximum_distance_km must be finite and positive')
    return float(value)


def finite_state(state):
    """Availability of all saved physical drivers, retaining input dimensions."""
    return np.all([np.isfinite(state[k].values) for k in STATE_UNITS], axis=0)


def validate_members(grid, table, *, require_samples=False, require_sources=False):
    """Validate saved state once per member and optionally its source cycles."""
    from .ensemble import member_ids
    from .data import utc

    ids = member_ids(grid)
    for member in ids or [None]:
        validate_grid(grid.sel(member=member, drop=True) if member is not None else grid,
                      table, require_samples=require_samples)
    if require_sources:
        for key in ('forecast_reference_time', 'cams_reference_time'):
            if key not in grid.attrs:
                raise ValueError(f'Missing source metadata {key}')
            utc(grid.attrs[key])
        cycle = np.datetime64(utc(grid.attrs['forecast_reference_time']).replace(tzinfo=None), 'ns')
        if np.any(grid.time_bounds.values[:, 0] < cycle):
            raise ValueError('Forecast intervals precede the ICON cycle')
    return ids


def validate_grid(grid, table, *, require_samples=False):
    """Validate one member's retained state and return its UTC interval bounds.

    Hourly gaps are allowed so consumers can assess daylight coverage. Missing
    state is allowed for ensemble members, whose availability is assessed later;
    quality flags must always be finite integer bitmasks. The requested sampling
    metadata is needed by hourly reconstruction, but not five-minute daily UV.
    """
    if grid.attrs.get('radiation_table_sha256') != table.sha256:
        raise ValueError('Radiation table differs from source grid')
    allow_missing = 'ensemble_members' in grid.attrs or 'minimum_member_fraction' in grid.attrs
    for name in (*STATE_UNITS, 'quality_flag'):
        if name not in grid or grid[name].dims != ('time', 'cell'):
            raise ValueError(f'Missing (time,cell) field: {name}')
        values = grid[name].values
        if (values.dtype.kind not in 'iuf' or np.any(np.isinf(values)) or np.any(values < 0)
                or ((not allow_missing or name == 'quality_flag') and not np.isfinite(values).all())):
            raise ValueError(f'Invalid {name}')
        if name in STATE_UNITS and grid[name].attrs.get('units') != STATE_UNITS[name]:
            raise ValueError(f'Invalid units for {name}')
    flags = grid.quality_flag.values
    if np.any(flags != np.floor(flags)) or np.any(flags > 65535):
        raise ValueError('Invalid quality flag bitmask')
    for name in ('latitude', 'longitude', 'altitude_m'):
        if (name not in grid or grid[name].dims != ('cell',)
                or grid[name].dtype.kind not in 'iuf' or not np.isfinite(grid[name]).all()):
            raise ValueError(f'Invalid {name}')
    if np.any(abs(grid.latitude) > 90) or np.any(abs(grid.longitude) > 180):
        raise ValueError('Invalid geographic coordinates')
    if 'cell' not in grid.coords or grid.cell.dims != ('cell',):
        raise ValueError('Native cell identifiers must be nonnegative integers')
    cells = grid.cell.values
    if cells.dtype.kind not in 'iu' or np.any(cells < 0):
        raise ValueError('Native cell identifiers must be nonnegative integers')
    if len(np.unique(cells)) != grid.sizes['cell']:
        raise ValueError('Duplicate native cells')
    if ('time_bounds' not in grid or grid.time_bounds.ndim != 2
            or grid.time_bounds.dims[0] != 'time' or grid.time_bounds.dtype.kind != 'M'):
        raise ValueError('Invalid time bounds')
    bounds = grid.time_bounds.values.astype('datetime64[ns]')
    if bounds.shape != (grid.sizes['time'], 2) or np.isnat(bounds).any():
        raise ValueError('Invalid time bounds')
    if (np.any(bounds[:, 1]-bounds[:, 0] != np.timedelta64(1, 'h')) or
            np.any(bounds[:, 0] != bounds[:, 0].astype('datetime64[h]')) or
            np.any(bounds[1:, 0] < bounds[:-1, 1])):
        raise ValueError('Expected ordered, nonoverlapping UTC hours')
    if ('time' not in grid.coords or grid.time.dims != ('time',) or grid.time.dtype.kind != 'M'
            or np.any(grid.time.values != bounds[:, 0] + np.timedelta64(30, 'm'))):
        raise ValueError('Expected interval midpoint time labels')
    if require_samples:
        samples = grid.attrs.get('solar_samples_per_hour')
        if (isinstance(samples, (bool, np.bool_)) or not isinstance(samples, Real)
                or samples not in SOLAR_SAMPLES):
            raise ValueError('solar_samples_per_hour must be 1,2,4,6,12')
    return bounds
