"""Inspect saved forecast support and physical inputs without calculating UV."""
import numpy as np

from .daily import _sources, utc_instant, valid_dates
from .coverage import daylight_coverage, eligible_members
from .ensemble import required_members
from .locations import (PointLocation, load_locations, plan_support,
                        prepare_point, support_requirements)
from .radiation import RadiationTable
from .state import validate_members


def _check_ranges(state, table, context):
    fields = {'ozone_du': 'ozone_du', 'pressure_pa': 'pressure_pa', 'aod550': 'aod550',
              'uv_albedo': 'albedo', 'effective_cloud_tau550': 'tau550'}
    for field, axis in fields.items():
        values = state[field].values
        lower, upper = table.axes[axis][0], table.axes[axis][-1]
        outside = np.isfinite(values) & ((values < lower) | (values > upper))
        if outside.any():
            t, c = np.argwhere(outside)[0]
            raise ValueError(f'{context}: {field}={values[t, c]:g} outside radiation table '
                             f'[{lower:g}, {upper:g}] at {state.time.values[t]}, '
                             f'cell {int(state.cell.values[c])}; check source units or local surface/elevation')


def _day_support(states, ids, day, minimum, spatial_minimum, spatial_fraction):
    """Count complete daylight intervals, retaining per-member spatial ordering."""
    n = states[0].sizes['cell']
    required_count = np.zeros(n, dtype=int)
    supplied_count = np.zeros(n, dtype=int)
    complete_count = np.zeros((len(states), n), dtype=int)
    for start in range(0, n, 256):
        sl = slice(start, min(start+256, n))
        coverage = daylight_coverage([state.isel(cell=sl) for state in states], day)
        required_count[sl] = coverage.required
        supplied_count[sl] = coverage.supplied
        complete_count[:, sl] = coverage.complete
    complete_cells, member_available = eligible_members(
        complete_count == required_count[None, :], spatial_minimum, spatial_fraction)
    count = int(member_available.sum())
    reasons = []
    if n < spatial_minimum:
        reasons.append('insufficient_native_support')
    if np.any(complete_count < required_count[None, :]):
        reasons.append('incomplete_daylight')
    if count < minimum:
        reasons.append('insufficient_ensemble_members' if len(ids) > 1 or minimum > 1 else 'incomplete_daylight')
    elif np.any(complete_cells[member_available] < n):
        reasons.append('partial_spatial_support')
    return dict(valid_date=day, available=count >= minimum,
                required_daylight_hours=required_count.tolist(),
                supplied_daylight_hours=supplied_count.tolist(),
                complete_member_count=count,
                reasons=list(dict.fromkeys(reasons)),
                members=[dict(member_id=member, complete_daylight_hours=complete_count[m].tolist(),
                              complete_cells=int(complete_cells[m]), available=bool(member_available[m]))
                         for m, member in enumerate(ids)])


def preflight(grid, locations, issued_at, *, days=None, dates=None, table=None):
    """Report source freshness, native support and daylight coverage without UV.

    Hour counts are aligned with each location's ``cell_ids``. Supplied counts
    describe interval presence; complete counts additionally require finite
    physical drivers within each member. Readiness applies the same member-first
    spatial coverage thresholds as daily publication. This checks saved inputs;
    it does not fetch forecasts or validate observational/scientific accuracy.
    """
    table = RadiationTable() if table is None else table
    catalog = load_locations(locations)
    ids = validate_members(grid, table, require_sources=True)
    present_ids = ids or [0]
    members = [grid.sel(member=m, drop=True) for m in ids] if ids else [grid]
    for member, state in zip(present_ids, members):
        _check_ranges(state, table, f'Source member {member}')
    issue = utc_instant(issued_at)
    sources, stale = _sources(grid.attrs, issue)
    resolved = valid_dates(grid, issued_at, days=days, dates=dates)
    expected, fraction, minimum = required_members(grid)
    if ids is None:
        expected, minimum = present_ids, 1
    rows = []
    for location in catalog.locations:
        plan = plan_support(grid, location)
        selected = len(plan.indices)
        spatial_minimum, spatial_fraction = support_requirements(location)
        if isinstance(location, PointLocation) and selected:
            states = [prepare_point(member, plan) for member in members]
        else:
            states = [member.isel(cell=plan.indices) for member in members]
        for member, state in zip(present_ids, states):
            _check_ranges(state, table, f'Location {location.id}, member {member}')
        coverage = [_day_support(states, present_ids, day, minimum, spatial_minimum, spatial_fraction)
                    for day in resolved]
        rows.append(dict(id=location.id, selected_cells=selected,
                         cell_ids=[int(v) for v in states[0].cell.values],
                         supported=selected >= spatial_minimum,
                         support_reason=None if selected >= spatial_minimum else 'insufficient_native_support',
                         required_cells=spatial_minimum, minimum_spatial_fraction=spatial_fraction,
                         dates=coverage))
    return dict(ready=not stale and all(day['available'] for row in rows for day in row['dates']),
                issued_at=issue.isoformat(), valid_dates=resolved, sources=sources, reasons=stale,
                radiation_table_sha256=table.sha256,
                ensemble=dict(member_ids=present_ids, requested_member_ids=expected,
                              minimum_member_fraction=fraction, required_member_count=minimum),
                locations=rows)
