# One location catalog for hourly and daily forecasts

Use `PointLocation` for individual sites and `RegionBand` for regional elevation
products. Stable `id` values identify the same location in hourly and daily
outputs; `label` controls display text. A location explicitly selects its physical
treatment:

| Location | Support and calculation |
|---|---|
| Native point | Nearest suitable cell within 5 km and 300 m; retain its coordinates, elevation, pressure and surface |
| Adjusted point | Nearest cell within 10 km; retain atmosphere/cloud state, adjust pressure to target altitude, use explicit target coordinates and UV albedo |
| Region band | Native cells within the bounding box and ±200 m of 1000, 2000 or 3000 m; spatial P90 within each member |

`maximum_distance_km` can override a point's distance limit. An adjusted point
requires `uv_albedo` between 0 and 0.85. A supplied horizon contains at least four
equally spaced elevation angles, starting at north and increasing clockwise.
Native points retain the model surface, so use adjusted treatment for a local
albedo or horizon. Regions require at least five selected cells and 95% spatial
coverage within each contributing member.

## Compute from a saved grid

```python
import xarray as xr
from icon_uv.locations import PointLocation, RegionBand, load_locations
from icon_uv.products import compute_points
from icon_uv.daily import compute_daily

locations = load_locations([
    PointLocation("bern", 46.95, 7.44, 540, label="Bern"),
    PointLocation("bern-site", 46.95, 7.44, 560, treatment="adjusted",
                  uv_albedo=0.05, horizon_degrees=(0.,) * 36),
    RegionBand("bernese-2000", (7.3, 46.4, 8.5, 46.9), 2000),
])
# Alternatively: load_locations("examples/shared_locations.json")
with xr.open_dataset("work/uv.nc") as grid:
    hourly = compute_points(grid, locations.points)
    daily = compute_daily(grid, locations, dates=["2026-09-07", "2026-09-09"])
```

Hourly point output is an xarray Dataset and preserves the ensemble member axis.
`compute_daily` returns a `DailyResult` for the specified local dates in
Europe/Zurich. It reconstructs five-minute midpoint samples before finding the
maximum 30-minute mean. Taking a maximum over hourly means would lose this
temporal information and produce a different value.

Daily products are ambient horizontal UVI by default. Set `terrain_screened=True`
to request screened daily point values with explicit horizons. Keep that geometry
visible to consumers: v4 records `uv_geometry` as `ambient_horizontal` or
`terrain_screened`. Native points and regions describe the open model surface.

## Publish with source provenance

The calculation API does not require an issuance time or a made-up file hash.
For a saved grid, use the file wrapper to stream its SHA-256, attach provenance
and apply issuance freshness checks:

```python
from icon_uv.daily import export_daily_file

payload = export_daily_file(
    "work/uv.nc", locations, issued_at="2026-09-07T06:00:00Z",
    dates=["2026-09-07", "2026-09-09"], output="work/daily.json",
)
```

To publish an already calculated result, call
`write_daily_json(daily, "work/daily.json", issued_at=..., input_sha256=...)`
with the actual source-grid SHA-256. JSON replacement is atomic. Issuance and
source age rules are described in [daily products](daily-products.md#export).

The shared API writes schema v4, adding point treatment and UV geometry while
supporting CTRL and ensemble inputs. `load_schema(payload)` selects the correct
packaged schema. Available rows report `support_uvi_range` and `support_uvi_median`
across contributing values, including adjusted-point values when applicable.
Legacy v1–v3 retain the original `native_uvi_range` and `native_uvi_median` names.
Legacy town catalogs through `export_daily` retain published
v1/v2/v3 formats; legacy `POI` and `compute_pois` also remain supported. Legacy
town entries use native-point treatment and keep their `town` output kind.
Legacy POI lists acquire canonical point IDs and explicit adjusted treatment.

## Check inputs before calculating products

```sh
uv run --no-sync icon-uv preflight --grid work/uv.nc \
  --locations examples/shared_locations.json \
  --issued-at "2026-09-07T06:00:00Z" --days 3
```

Preflight checks saved-grid contracts, source freshness, location support and
temporal input coverage without running the UV calculation. It reports which
locations lack suitable cells or enough daylight input. These checks help catch
an incompatible saved forecast before product generation; they do not establish
scientific forecast skill or contact download services.
The command prints JSON by default; `--output work/preflight.json` also saves it.
Exit status is zero when ready and one when coverage/support is insufficient.

`points` aliases `poi`, and `--locations` aliases `--catalog` for daily output.
Choose a positive `--days N`, `--days all`, or an explicit list such as
`--dates 2026-09-07 2026-09-09`. Date lists and `--days` are mutually exclusive.
The `day` field remains the offset from issuance's local date, even for a list
with gaps. Ordinary CLI errors are concise; put `--debug` before the command
(for example, `icon-uv --debug daily ...`) for a traceback. Daily CLI screening
is requested with `--terrain-screened`.
