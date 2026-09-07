"""Shared location definitions and explicit native/adjusted support selection."""
from dataclasses import asdict, dataclass
from copy import deepcopy
from collections.abc import Mapping
from numbers import Real
from .state import positive_distance
import json
from pathlib import Path

import numpy as np

NATIVE_DISTANCE_KM = 5.
NATIVE_HEIGHT_TOLERANCE_M = 300.
REGION_HEIGHT_TOLERANCE_M = 200.
REGION_MINIMUM_CELLS = 5
REGION_MINIMUM_FRACTION = .95
REGION_QUANTILE = .9


def _finite_number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


@dataclass(frozen=True)
class PointLocation:
    id: str
    latitude: float
    longitude: float
    altitude_m: float
    label: str | None = None
    treatment: str = 'adjusted'
    uv_albedo: float | None = None
    horizon_degrees: tuple[float, ...] | None = None
    maximum_distance_km: float | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError('Location id must be a nonempty string')
        if self.label is not None and not isinstance(self.label, str):
            raise ValueError('Location label must be a string')
        for name in ('latitude', 'longitude', 'altitude_m'):
            object.__setattr__(self, name, _finite_number(getattr(self, name), name))
        if self.uv_albedo is not None:
            object.__setattr__(self, 'uv_albedo', _finite_number(self.uv_albedo, 'uv_albedo'))
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError('Invalid point coordinates')
        if self.treatment not in ('native', 'adjusted'):
            raise ValueError('Point treatment must be native or adjusted')
        distance = self.maximum_distance_km
        if distance is not None:
            object.__setattr__(self, 'maximum_distance_km', positive_distance(distance))
        if self.treatment == 'adjusted':
            if not -100 <= self.altitude_m <= 5000:
                raise ValueError('Adjusted point requires altitude -100..5000 m')
            if self.uv_albedo is not None and not 0 <= self.uv_albedo <= .85:
                raise ValueError('UV albedo must be in 0..0.85')
        elif self.uv_albedo is not None or self.horizon_degrees is not None:
            raise ValueError('Native points retain model surface; use adjusted treatment for local surface/horizon')
        if self.horizon_degrees is not None:
            h = np.asarray(self.horizon_degrees, float)
            if h.ndim != 1 or len(h) < 4 or not np.isfinite(h).all() or np.any((h < 0) | (h > 90)):
                raise ValueError('Provide >=4 finite horizon elevations 0..90, equally spaced from north')
            object.__setattr__(self, 'horizon_degrees', tuple(float(v) for v in h))

    def to_entry(self):
        entry = {k: v for k, v in asdict(self).items() if v is not None}
        return json.loads(json.dumps(dict(entry, kind='point', label=self.label or self.id)))


@dataclass(frozen=True)
class RegionBand:
    id: str
    bbox: tuple[float, float, float, float]
    altitude_m: float
    label: str | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError('Location id must be a nonempty string')
        if self.label is not None and not isinstance(self.label, str):
            raise ValueError('Location label must be a string')
        try:
            bbox = tuple(_finite_number(v, 'bbox coordinate') for v in self.bbox)
            w, s, e, n = bbox
        except TypeError as exc:
            raise ValueError('Region bbox must have four numeric coordinates') from exc
        object.__setattr__(self, 'altitude_m', _finite_number(self.altitude_m, 'altitude_m'))
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90) or self.altitude_m not in (1000, 2000, 3000):
            raise ValueError('Invalid region bounds or unsupported altitude')
        object.__setattr__(self, 'bbox', bbox)

    def to_entry(self):
        return json.loads(json.dumps(dict(asdict(self), kind='region_altitude', label=self.label or self.id)))


@dataclass(frozen=True)
class LocationCatalog:
    locations: tuple[PointLocation | RegionBand, ...]
    _catalog: dict

    @property
    def catalog(self):
        return deepcopy(self._catalog)

    @property
    def points(self):
        return tuple(p for p in self.locations if isinstance(p, PointLocation))


def location_from_entry(entry):
    if not isinstance(entry, Mapping):
        raise ValueError('Location entry must be an object')
    try:
        kind = entry.get('kind', 'point' if 'name' in entry else None)
        if kind == 'region_altitude':
            return RegionBand(entry['id'], entry['bbox'], entry['altitude_m'], entry.get('label'))
        if kind not in ('town', 'point'):
            raise ValueError('Unsupported location kind')
        legacy_poi = 'name' in entry and 'id' not in entry
        if kind == 'town' and any(k in entry for k in ('treatment', 'uv_albedo', 'horizon_degrees')):
            raise ValueError('Use kind point for explicit surface treatment')
        return PointLocation(
            entry['name'] if legacy_poi else entry['id'], entry['latitude'], entry['longitude'],
            entry['altitude_m'], entry.get('label'),
            entry.get('treatment', 'native' if kind == 'town' else 'adjusted'),
            entry.get('uv_albedo'), entry.get('horizon_degrees'), entry.get('maximum_distance_km'))
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Invalid location entry: {exc}') from exc


def load_locations(source):
    """Read one shared catalog, legacy town catalogs, or legacy POI JSON lists."""
    if isinstance(source, LocationCatalog):
        return source
    if isinstance(source, (str, Path)):
        source = json.loads(Path(source).read_text(encoding='utf-8'))
    if isinstance(source, dict):
        if source.get('catalog_version', 1) not in (1, 2):
            raise ValueError('Unsupported catalog_version')
        catalog = source
        entries = source.get('entries', [])
    else:
        try:
            entries = list(source)
        except TypeError as exc:
            raise ValueError('Locations must be a catalog or a list') from exc
        entries = [e.to_entry() if isinstance(e, (PointLocation, RegionBand)) else e for e in entries]
        catalog = {'catalog_version': 2, 'entries': entries}
    if not isinstance(entries, (list, tuple)):
        raise ValueError('Catalog entries must be a list')
    locations = tuple(location_from_entry(e) for e in entries)
    if not locations or len({p.id for p in locations}) != len(locations):
        raise ValueError('Nonempty, unique catalog identifiers required')
    # Fail before computation if metadata cannot be represented in the output.
    catalog = json.loads(json.dumps(catalog, allow_nan=False))
    for entry, location in zip(catalog['entries'], locations):
        if isinstance(location, PointLocation) and entry.get('kind') != 'town':
            entry.pop('name', None)
            entry.update(location.to_entry())
    return LocationCatalog(locations, catalog)


@dataclass(frozen=True)
class SupportPlan:
    location: PointLocation | RegionBand
    indices: np.ndarray
    distances_km: np.ndarray


def plan_support(grid, location):
    """Select native cells once; selection never depends on member weather."""
    lat, lon, height = (grid[k].values for k in ('latitude', 'longitude', 'altitude_m'))
    if any(np.ndim(v) != 1 or not np.isfinite(v).all() for v in (lat, lon, height)):
        raise ValueError('Invalid native geometry')
    if isinstance(location, RegionBand):
        w, s, e, n = location.bbox
        indices = np.flatnonzero((lon >= w) & (lon <= e) & (lat >= s) & (lat <= n) & (abs(height-location.altitude_m) <= REGION_HEIGHT_TOLERANCE_M))
        return SupportPlan(location, indices, np.array([]))
    phi, origin = np.deg2rad(lat), np.deg2rad(location.latitude)
    a = np.sin((phi-origin)/2)**2 + np.cos(phi)*np.cos(origin)*np.sin(np.deg2rad(lon-location.longitude)/2)**2
    distances = 12742*np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    limit = location.maximum_distance_km or (10. if location.treatment == 'adjusted' else NATIVE_DISTANCE_KM)
    allowed = distances <= limit
    if location.treatment == 'native':
        allowed &= abs(height-location.altitude_m) <= NATIVE_HEIGHT_TOLERANCE_M
    elif 'bbox' in grid.attrs:
        w, s, e, n = json.loads(grid.attrs['bbox'])
        if not (w <= location.longitude <= e and s <= location.latitude <= n):
            allowed[:] = False
    indices = np.flatnonzero(allowed)
    # Tie break by stable native ID, independently of input cell order.
    indices = indices[np.lexsort((grid.cell.values[indices], distances[indices]))[:1]]
    return SupportPlan(location, indices, distances[indices])


def prepare_point(grid, plan):
    """Retain source cloud/composition, optionally adjust pressure and surface."""
    point = plan.location
    if not isinstance(point, PointLocation) or len(plan.indices) != 1:
        raise ValueError('Point needs one suitable native cell')
    local = grid.isel(cell=plan.indices).copy(deep=True)
    if point.treatment == 'adjusted':
        pressure_attrs = local.pressure_pa.attrs.copy()
        local['pressure_pa'] = local.pressure_pa*np.exp(-(point.altitude_m-float(local.altitude_m.values[0]))/8434)
        local.pressure_pa.attrs = pressure_attrs
        if point.uv_albedo is not None:
            local['uv_albedo'] = local.pressure_pa*0 + point.uv_albedo
            local.uv_albedo.attrs = {'units': '1'}
        for name in ('latitude', 'longitude', 'altitude_m'):
            local[name] = ('cell', [getattr(point, name)])
        local['quality_flag'] = local.quality_flag.astype('uint16') | 16 | (32 if point.horizon_degrees is not None else 0)
    return local
