# One location catalog for hourly and daily forecasts

Define a `PointLocation` with coordinates and elevation, or a `RegionBand` for a
regional elevation summary. Both hourly and daily calculations use these same
location definitions and surface defaults. Stable `id` values identify locations;
`label` supplies display text.

This API and its defaults are available in **icon-uv 0.2.0 or later**.
The [repository installation](index.md#try-it-without-credentials) includes the example catalogs.

## Calculate and publish

```python
import xarray as xr
from icon_uv import (
    PointLocation, RegionBand, load_locations,
    compute_points, compute_daily, export_daily_file,
)

locations = load_locations([
    PointLocation("zermatt", 46.017536, 7.746568, 1617, label="Zermatt"),
    RegionBand("valais-3000", (7.0, 45.9, 8.4, 46.4), 3000),
])
# Or: locations = load_locations("examples/shared_locations.json")
with xr.open_dataset("work/uv.nc") as grid:
    hourly = compute_points(grid, locations.points)
    daily = compute_daily(grid, locations, dates=["2026-09-07", "2026-09-08"])

payload = export_daily_file(
    "work/uv.nc", locations, issued_at="2026-09-07T06:00:00Z",
    dates=["2026-09-07", "2026-09-08"], output="work/daily.json",
)
```

Choose dates matching your forecast. `compute_points` returns hourly means in an
xarray Dataset and retains ensemble members. `compute_daily` returns a
`DailyResult`: it reconstructs five-minute samples and finds the maximum
30-minute mean for each Swiss local date. It also includes regional products.
Hourly means cannot recover this daily peak exactly.

Calculation does not require an issuance time or file hash. `export_daily_file`
adds the saved grid's SHA-256 and freshness checks, and optionally writes JSON.
For an existing result, use `write_daily_json(daily, output_path,
issued_at=..., input_sha256=...)` with the actual source-grid hash.
Publication replaces JSON atomically; see [daily products](daily-products.md#export).

## Location defaults

| Location | Calculation |
|---|---|
| Point (default `treatment="adjusted"`) | Nearest cell within 10 km supplies cloud, ozone, aerosol and surface state; recompute solar geometry and pressure at the requested coordinates/elevation |
| Region band | Native cells inside the box and within ±200 m of 1000, 2000 or 3000 m; daily spatial P90 within each member |
| Point with `treatment="native"` | Nearest cell within 5 km and 300 m of the target; retain that cell's coordinates, elevation and surface |

Coordinates are WGS84 degrees, elevations are metres above sea level and boxes
use `(west, south, east, north)`. `maximum_distance_km` overrides a point's distance
limit. Region bands need at least five selected cells and 95% spatial coverage
within each contributing member.

An omitted `uv_albedo` inherits the selected cell's saved UV albedo, retaining its
time and ensemble variation. Grids made by `compute_grid` estimate it as
`0.05 + 0.75 × ICON snow_fraction`, from `SNOWC`. This is an experimental snow
proxy, not a measured UV albedo. It is distinct from broadband `ALB_RAD`, used
only for fitting the shortwave cloud response. Missing source values remain
missing. For a specific site, `uv_albedo=...` overrides the estimate with a finite
constant between 0 and 0.85.

Points and regions default to **ambient horizontal UV**: no local horizon is
applied. A town reference point therefore does not impose valley-floor shade on
a surrounding mountain destination. It still has one target elevation and one
source cloud/snow column; regional elevation bands supply broader mountain context.
Elevation correction does not locate the point above or below a cloud layer.

## One example with a supplied horizon

The [Davos catalog](https://github.com/ofuhrer/icon-uv/blob/main/examples/davos.json)
contains the project's explicit site example. Its 72 horizon angles derive from
swisstopo terrain profiles; UV albedo 0.05 is an assumption, not a measurement.
See [point outputs](outputs.md#point-forecasts) for provenance and limitations.

```python
site = load_locations("examples/davos.json")
with xr.open_dataset("work/uv.nc") as grid:
    hourly = compute_points(grid, site.points)
    screened_daily = compute_daily(
        grid, site, dates=["2026-09-07"], terrain_screened=True,
    )
```

`horizon_degrees` contains at least four equally spaced elevation angles from
north clockwise, between 0° and 90°. With a horizon, hourly output includes
`terrain_screened_uvi` alongside ambient `uvi`; without one, the screened field
is unavailable. Screened daily output requires a catalog containing only adjusted
points with explicit horizons. `uv_geometry` identifies the chosen daily geometry.
The package accepts supplied horizon arrays and does not generate them or depend
on HORAYZON.

## CLI and compatibility

```sh
uv run --no-sync icon-uv points --grid work/uv.nc \
  --locations examples/shared_locations.json --output work/points.nc
uv run --no-sync icon-uv daily --grid work/uv.nc \
  --locations examples/shared_locations.json --days 3 \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/daily.json
```

The shared catalog uses `catalog_version: 2`, `kind: "point"` or
`kind: "region_altitude"`, and the same field names as Python. New point entries
may omit `treatment`, albedo and horizon. Set `treatment: "native"` explicitly to
retain native-cell matching. Native points do not accept local surface overrides.

New shared products use **daily-uv-v5**, allowing inherited point albedo.
Published v1–v4 schemas remain unchanged. Legacy `kind: "town"` catalogs retain
native matching and their existing v1/v2/v3 export formats. `POI`, `compute_pois`,
legacy POI JSON lists, `poi` and `--catalog` remain compatibility entry points.
See [JSON contracts](daily-products.md#reading-the-payload) for version selection.

`daily` accepts positive `--days N`, `--days all`, or explicit `--dates` (mutually
exclusive with `--days`). `--terrain-screened` selects screened daily output.
`preflight` accepts the same grid, locations, issuance and date selection to check
support and coverage before calculation; it prints JSON and exits one when not
ready. Put `--debug` before a command for a traceback.
