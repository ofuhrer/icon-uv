# Output reference

## Hourly grid

`icon-uv run` writes a compressed NetCDF dataset on native ICON cell centres.
The main dimensions are `time` and `cell`; latitude, longitude and model altitude
are cell coordinates. Original cell IDs and the grid UUID are preserved.
For polygon rendering, obtain triangle vertices from the source ICON grid.

NetCDF uses lossless compression and chunked storage, preserving each input
variable's dtype. Computed grid diagnostics use float32; float64 atmospheric
inputs and coordinates retain their precision and quality flags remain integers.
Writing a file does not introduce a separate float64-to-float32 conversion.
Scientific UVI values are not rounded to display integers.

| Variable | Units | Meaning |
|---|---|---|
| `uvi` | 1 | Hourly mean all-sky UV Index on an open horizontal surface |
| `clear_sky_uvi` | 1 | UV Index with the same atmosphere and surface but no cloud |
| `erythemal_direct` | W/m² | Direct erythemal irradiance on a horizontal surface |
| `erythemal_diffuse` | W/m² | Diffuse erythemal irradiance |
| `uvi_sample_max` | 1 | Largest reconstructed solar-sample UVI within the hour |
| `effective_cloud_tau550` | 1 | Inferred cloud optical thickness at 550 nm |
| `cloud_scale` | 1 | Scalar extension of the table response where needed |
| `quality_flag` | bit mask | Calculation conditions listed below |

`uvi = 40 * (erythemal_direct + erythemal_diffuse)`. Direct irradiance here is
horizontal, rather than direct-normal irradiance. The sample maximum and the
hourly mean describe different temporal quantities.

`time` is the UTC interval midpoint; `time_bounds(time, bounds)` supplies the
hour's two endpoints. The dataset retains the hourly shortwave forcing, pressure,
ozone, aerosol optical depth and surface state needed to recompute point and
daily products. Attributes record source cycles, input hashes, radiation-table
identity, calculation settings and package version.

## Quality flags

Flags are combined by bitwise OR. For example, `flag & 64` tests for low-sun
samples; several conditions can apply to the same value.

| Bit | Meaning |
|---:|---|
| 1 | Shortwave exceeds the calculated clear-sky response; a scalar extension is used |
| 2 | Shortwave falls below the minimum cloud-table response; a scalar extension is used |
| 4 | Weak or absent solar signal; cloud inversion carries little information |
| 8 | Nonmonotonic cloud response; the earliest bracketing branch is selected |
| 16 | Atmospheric-column adjustment for a point's elevation |
| 32 | Approximate terrain screening applied |
| 64 | A daylight sample has solar zenith angle above 78° |
| 128 | Missing required ICON input; affected UV values are NaN |

These flags describe calculation conditions. Missing driver variables, invalid units and
out-of-range table inputs raise errors; missing input samples remain NaN. Use `icon_uv.check_grid` to check saved
fields and reconstruct their shortwave forcing:

```sh
uv run --no-sync python -m icon_uv.check_grid \
  --grid work/uv.nc --output work/grid_check.json
```

## Point forecasts

`compute_points(grid, locations.points)` returns hourly data indexed by
`time, poi`, with a `member` axis for ensembles. The [location API](location-api.md)
defines point matching, default ICON-derived albedo and optional site overrides.
Output retains target and source coordinates/elevations, source cell ID/distance,
treatment, effective UV albedo and supplied horizon.

Pressure is adjusted to target elevation using an 8434 m scale height. The source
cell supplies cloud state, ozone and aerosol. The radiation table must match the
source grid's table identity. Inherited albedo retains time/member variation;
explicit fixed albedo is recorded with the point's effective surface state.

`uvi` and `clear_sky_uvi` describe ambient horizontal UV. With a supplied horizon,
`terrain_screened_uvi` blocks direct sunlight below the horizon and scales diffuse
irradiance by the isotropic sky-view factor, `mean(cos(horizon)²)`. Without a
horizon, the screened field is unavailable (NaN). Terrain reflection and
anisotropic diffuse radiation are omitted. Elevation adjustment retains the
source cloud column and does not infer whether a summit lies above clouds.

The [Davos example](https://github.com/ofuhrer/icon-uv/blob/main/examples/davos.json)
is the supplied site example: 72 horizon samples at 5° azimuth spacing, extracted
from [swisstopo terrain profiles](https://api3.geo.admin.ch/rest/services/profile.json)
on 5 September 2026 using a 20 km radius and 401 samples per ray. Horizon angles
are rounded to 0.01°; point altitude is 1588.2 m. UV albedo 0.05 is an explicit
assumption. This is terrain-derived example geometry, not a surveyed instrument
installation or measured albedo. `load_locations` accepts this legacy POI list
for both hourly and daily calculations.

## Daily JSON

See [daily products](daily-products.md) for the catalog format, aggregation,
statuses and schema. Daily values are reconstructed rolling peaks; taking the
maximum of `uvi` would instead produce a maximum of clock-hour means.

## Comparing observations

`icon_uv.products.compare_observations(forecast, observations)` returns matched
bias, MAE and RMSE. Both inputs need `uvi(time, poi)` in units `1`, unique named
coordinates and identical hourly `time_bounds`. Observation data also need
boolean `qc_good(time, poi)`. The caller supplies the instrument-specific unit,
time-support and quality-control adaptation. Comparisons use shared times and
points, excluding missing values and observations with `qc_good=False`.

## Ensemble dimensions

With the default ensemble download, member-dependent ICON and UV fields have
`(member, time, cell)` dimensions; POI forecasts have `(member, time, poi)`.
`member` identifies CTRL 0 and perturbed members 1–20. Native coordinates, `time_bounds(time, bounds)`, and interpolated CAMS
`ozone_du(time, cell)` / `aod550(time, cell)` are shared across members. Attributes record the expected member
IDs and the minimum coverage fraction. Missing samples remain NaN with quality
flag 128; daily reductions require 90% complete member products by default.

For hourly point or grid summaries, reduce the computed UV values across
`member` and mask insufficient coverage, for example
`points.uvi.median("member").where(points.uvi.count("member") >= 19)` for the
default 21-member request. Adapt the count if you change the coverage threshold. For a daily
UV Index product, use [daily export](daily-products.md#ensemble-products): it
computes member daily peaks before reduction. Averaging atmospheric inputs first
would lose cloud uncertainty and alter the nonlinear UV calculation.

Download with `fetch-icon --control` to retain the original single-member
`(time, cell)` / `(time, poi)` layout. Existing CTRL files remain supported.
