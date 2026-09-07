"""Daylight completeness and member eligibility shared by preflight and UV."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from .radiation import solar_geometry
from .state import finite_state


def local_day_bounds(value):
    day = date.fromisoformat(str(value))
    zone = ZoneInfo('Europe/Zurich')
    ends = [datetime.combine(day + timedelta(days=d), time(), zone) for d in (0, 1)]
    return tuple(np.datetime64(t.astimezone(timezone.utc).replace(tzinfo=None), 'ns') for t in ends)


def daylight_hours(value, latitude, longitude):
    """UTC hours containing any sun-above-horizon one-minute midpoint."""
    start, end = local_day_bounds(value)
    hours = np.arange(start, end, np.timedelta64(1, 'h'))
    minute = hours[:, None] + np.arange(60)[None, :] * np.timedelta64(1, 'm') + np.timedelta64(30, 's')
    z, _, _ = solar_geometry(minute[:, :, None], np.asarray(latitude)[None, None, :],
                             np.asarray(longitude)[None, None, :])
    return hours, np.any(z < 90, axis=1)


@dataclass
class DaylightCoverage:
    hours: np.ndarray
    rows: np.ndarray
    required: np.ndarray
    supplied: np.ndarray
    complete: np.ndarray


def daylight_coverage(states, day):
    """Count required/present hours per cell and finite hours per member/cell.

    States share time bounds and geometry. Call on cell chunks to bound the
    minute-resolution solar arrays. Missing nighttime state does not affect
    completeness; a missing daylight interval invalidates that member/cell.
    """
    source = states[0]
    hours, required = daylight_hours(day, source.latitude.values, source.longitude.values)
    lookup = {t: i for i, t in enumerate(source.time_bounds.values[:, 0])}
    rows = np.array([lookup.get(hour, -1) for hour in hours], dtype=int)
    present = rows >= 0
    complete = np.array([(required[present] & finite_state(s.isel(time=rows[present]))).sum(axis=0)
                         for s in states])
    return DaylightCoverage(hours, rows, required.sum(axis=0), required[present].sum(axis=0), complete)


def eligible_members(valid_cells, minimum_cells, minimum_fraction):
    """Apply spatial support within each member before counting members."""
    counts = valid_cells.sum(axis=1)
    return counts, (counts >= minimum_cells) & (counts >= minimum_fraction * valid_cells.shape[1])
