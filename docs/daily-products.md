# Daily map products

Daily products turn a saved UV grid and a [shared location catalog](location-api.md)
into JSON with daily peaks, rounded values, categories and source/support details.
Points use the same elevation, albedo and horizon choices as hourly forecasts;
regions summarize native cells in an elevation band. Ambient horizontal UV is
the default.

## Prepare the grid

Follow the [download workflow](index.md#calculate-uv-fields)
with input coverage for every requested daylight period. Twelve solar samples
per hour align cloud fitting with daily five-minute reconstruction:

```sh
uv run --no-sync icon-uv run --icon work/icon.nc --cams work/cams.nc \
  --samples 12 --output work/uv.nc
```

Grids calculated with the default four samples per hour also work. The daily
calculation always reconstructs five-minute solar geometry from saved hourly
cloud state.

## Export

Use an issuance timestamp with a timezone, normally the morning of the ICON cycle:

```sh
uv run --no-sync icon-uv daily --grid work/uv.nc \
  --locations examples/shared_locations.json --days 4 \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/daily.json
```

Issuance determines local dates and source-age checks. ICON may be at most
24 hours old and CAMS at most 48 hours old. Future cycles raise an error; stale
cycles produce unavailable entries. Reusing the same inputs, catalog and
issuance produces the same payload. [Python publication](location-api.md#publish-from-a-saved-grid)
provides the same checks with a source file hash.

Date choices are:

- Default: today and tomorrow in Europe/Zurich.
- `--days N`: exactly N dates starting on the issuance date.
- `--days all`: through the last supplied daylight date; omit a trailing night-only date.
- `--dates YYYY-MM-DD YYYY-MM-DD`: an explicit list, including gaps if needed.

`--days` and `--dates` are mutually exclusive. In JSON, `day` is the offset from
the local issuance date; `valid_dates` lists the requested dates. Short input
coverage produces unavailable values, never a partial-day maximum.

## Peak, rounding and categories

The daily peak is the maximum 30-minute mean over a Swiss local day, evaluated
at five-minute window starts. Each window averages six five-minute midpoint
samples. Day boundaries account for daylight saving time. All hourly intervals
intersecting daylight must be present; missing night-only intervals are harmless.

For a point, evaluate UV at its target coordinates/elevation using the selected
cell's cloud and surface state. For a region, first find each native cell's daily
peak, then take their **spatial P90**. Region bands use cells inside the box and
within ±200 m of the requested elevation. At least five cells and 95% complete
spatial coverage are required within each contributing member. Cells may peak at
different times: the regional value is a percentile of their individual maxima.

Round only after all temporal, spatial and ensemble reductions, using
`floor(UVI + 0.5)`. Category follows the displayed integer:

| Display UVI | Category |
|---|---|
| 0–2 | `low` |
| 3–5 | `moderate` |
| 6–7 | `high` |
| 8–10 | `very_high` |
| 11 and above | `extreme` |

Values above 11 retain their number. Missing values use `null`, distinct from zero.
For native-grid clear-sky peaks, `daily_cells(grid, date, clear_sky=True)` uses
the same timing and coverage checks with cloud optical depth zero and scaling one.
The [map example](meteoswiss-map.md#map-layers) exports both gridded quantities.

## Ensemble products

`fetch-icon` defaults to CTRL and 20 perturbed members. UV is calculated
independently for each member, preserving its cloud and surface conditions.
CAMS composition and the radiation table are shared. The daily reduction order is:

1. Calculate each point's or native cell's daily peak within each member.
2. For a region, take the spatial P90 within that member.
3. Take the ensemble median (P50) of the unrounded member products.
4. Round once for display.

`--ensemble-quantile 0.75` selects P75 instead; Python accepts
`ensemble_quantile=.75`. Averaging the atmospheric inputs or taking a maximum
of hourly ensemble medians would produce a different quantity.

The top-level `ensemble` object records requested member IDs, count, quantile
and reduction method. Available rows include member values in that order,
P10/P50/P90 and the member fractions with **unrounded** UVI at least 3, 6, 8 or 11.
These are uncalibrated frequencies, not confidence intervals: they do not include
all composition, radiation, terrain or representativeness errors. See
[validation](validation.md) for the scope of existing CTRL measurement comparisons.

By default, 90% of requested members must contribute complete products: **19 of 21**.
Incomplete members remain null and are excluded locally for that location/day.
Accepted missing members produce `degraded` status and `partial_ensemble_support`;
too few produce `unavailable`. Region spatial coverage is checked within each
member before counting it. No missing value is treated as zero.

`fetch-icon --minimum-member-fraction 0.8` changes the coverage threshold, which
is saved for downstream products. Download coverage counts usable
member × time × cell × required-field samples; a missing accumulated-radiation
boundary can invalidate both adjacent intervals. Global download coverage does
not guarantee local product coverage.

Use `fetch-icon --control` (Python: `fetch_icon(..., ensemble=False)`) for CTRL
only. All downstream commands detect the input's member layout automatically.

## Reading the payload

Every export uses the **daily-uv** contract (`schema: "daily-uv"`).
`contract_sha256` identifies the exact bundled schema file. Top-level metadata includes issuance,
timezone, valid dates, peak definition, source cycle ages, grid/catalog/table
hashes, UV geometry and optional ensemble information. Each row records its
location, date, day offset, status/reasons, selected/valid support counts,
raw UVI, display UVI and category.

Available rows also report aggregation, source cell IDs, quality flags,
`support_uvi_range`, `support_uvi_median` and peak-window time range. Point rows
include source coordinates/elevation and the height difference from the target.
CTRL points have a single peak time; regional and ensemble products report ranges.
The support UVI summaries describe contributing values after the selected point
treatment, including its elevation and albedo choices.

| Status | Meaning |
|---|---|
| `ok` | Complete selected spatial support for every requested member product |
| `degraded` | Accepted partial spatial or ensemble support |
| `unavailable` | Data age, daylight coverage or location support rules fail |

Keep status and reasons visible in renderers. Global input errors leave an
existing output file unchanged; consumers should check its issuance. JSON writes
are atomic and exclude NaN/Infinity.

```python
import json
from icon_uv.schema import load_schema, validate_daily

with open("work/daily.json") as stream:
    payload = json.load(stream)
schema = load_schema()
validate_daily(payload)  # requires jsonschema, included in the dev setup
```

`load_schema` needs no validator dependency. `validate_daily` checks structure
and date/time formats. Exporter checks additionally enforce semantic rules such
as freshness, date pairing, rounding and support counts.

The single [schema](https://github.com/ofuhrer/icon-uv/blob/main/icon_uv/data/daily-uv.schema.json)
covers points, regions, arbitrary dates and optional ensemble summaries. Fields
and geometry do not depend on how the catalog was constructed or which publisher
was called. `uv_geometry`, `valid_dates`, `support_uvi_range` and
`support_uvi_median` have the same meaning throughout the API.
