# Daily map products

`icon-uv daily` turns a saved UV grid and a location catalog into JSON for today
and tomorrow in Europe/Zurich. The output contains raw UVI, rounded display
values, categories and the source/support information needed by a renderer.

## Prepare the grid

Use the [README download workflow](../README.md#calculate-uv-fields) to obtain
ICON and CAMS inputs covering daylight on both dates. The `run` command uses
four solar samples per hour. For twelve samples per hour in the cloud fit,
compute the grid through Python:

```python
import xarray as xr
from icon_uv.data import load_cams, write_netcdf
from icon_uv.products import compute_grid

with xr.open_dataset("work/icon.nc") as icon:
    grid = compute_grid(icon.load(), load_cams("work/cams.grib"), samples=12)
write_netcdf(grid, "work/uv.nc")
```

The daily calculation reconstructs UV at five-minute midpoints from the saved
hourly cloud state. Either input-grid sampling choice is accepted; twelve
samples also evaluates the cloud fit on that five-minute spacing.

## Define locations

Save a JSON object with an `entries` list. Each entry needs a unique `id`, a
`label`, a `kind` and the geometry for that kind:

```json
{
  "catalog_version": 1,
  "entries": [
    {
      "id": "bern",
      "kind": "town",
      "label": "Bern",
      "latitude": 46.95,
      "longitude": 7.44,
      "altitude_m": 540
    },
    {
      "id": "bernese-2000",
      "kind": "region_altitude",
      "label": "Bernese Alps, 2000 m",
      "bbox": [7.3, 46.4, 8.5, 46.9],
      "altitude_m": 2000
    }
  ]
}
```

Coordinates are WGS84 degrees and elevations are metres above sea level.
Bounding boxes use `[west, south, east, north]`. The full
[example catalog](../examples/product_locations.json) has Swiss towns
and mountain regions; adapt its locations and boundaries to your product.
For the 20-town and six-region map layout, use the
[MeteoSwiss map example](meteoswiss-map.md).

| Kind | Native-cell selection | Reported value |
|---|---|---|
| `town` | Nearest cell within 5 km and 300 m of target elevation | That cell's daily peak |
| `region_altitude` | Cells inside the box and within ±200 m of 1000, 2000 or 3000 m | 90th percentile of cell daily peaks |

A region requires at least five selected cells, with at least 95% providing
complete daylight coverage. Each cell keeps its own cloud, pressure and surface
state. Regional cells may peak at different times; the aggregate represents a
spatial percentile of their individual daily maxima.

## Export

Set `ISSUED_AT` to the intended timezone-aware issuance timestamp, for example
06 UTC on the chosen ICON cycle's date:

```sh
ISSUED_AT="YYYY-MM-DDT06:00:00Z"
uv run --no-sync icon-uv daily \
  --grid work/uv.nc --catalog my-locations.json \
  --issued-at "$ISSUED_AT" --output work/daily-uv.json
```

The timestamp controls both local valid dates and source-age checks. Reusing it
with the same inputs and catalog produces the same payload. ICON may be at most
24 hours old and CAMS at most 48 hours old at issuance. Future cycles raise an
error; stale cycles yield unavailable entries.

## Peak, rounding and categories

The daily peak is the maximum reconstructed 30-minute mean, evaluated at
five-minute window starts within the local day. A window averages six
five-minute midpoint samples. Day boundaries account for daylight saving time.
All hourly intervals intersecting daylight at a cell must be present; missing
night-only intervals do not make that cell unavailable.

Round after temporal and spatial aggregation with `floor(UVI + 0.5)`.
Category is based on that displayed integer:

| Display UVI | Category string |
|---|---|
| 0–2 | `low` |
| 3–5 | `moderate` |
| 6–7 | `high` |
| 8–10 | `very_high` |
| 11 and above | `extreme` |

Values above 11 retain their numerical value. Missing values use JSON `null`,
which is distinct from a valid UVI of zero.

## Reading the payload

Top-level fields include schema/contract versions, `issued_at`, `timezone`,
`peak_definition`, `category_basis`, source reference times and ages, input/
catalog/table hashes, model-scope metadata and `entries`.

Each entry includes its catalog location, `valid_date`, `day` (0 or 1), `status`,
`reasons`, selected/valid cell counts, `uvi`, `display_uvi` and `category`.
Available entries also include the aggregation method, contributing cell IDs,
UVI range/median, combined quality flags and the range of peak-window starts.
Town entries include the selected source point, height difference and peak time.

| Status | Meaning |
|---|---|
| `ok` | All selected cells have complete required daylight coverage |
| `degraded` | A region has partial coverage that still meets the 95% rule |
| `unavailable` | Data age, coverage or native support rules fail; UV fields are null |

Use these states and reasons when rendering. Global input errors leave an
existing output file unchanged; consumers can use its issuance timestamp to
identify an older result. JSON replacement is atomic and excludes NaN/Infinity.

The [packaged JSON Schema](../icon_uv/data/daily-uv-v1.schema.json) describes the
structural format. With the development dependencies installed:

```python
import json
from importlib.resources import files
import jsonschema

schema = json.loads((files("icon_uv") / "data/daily-uv-v1.schema.json").read_text())
with open("work/daily-uv.json") as stream:
    payload = json.load(stream)
jsonschema.validate(payload, schema)
```

Schema validation checks structure. Calendar pairing, freshness at consumption,
rounding consistency and support-count relationships also have semantic rules
implemented by the exporter and covered by the test suite.
