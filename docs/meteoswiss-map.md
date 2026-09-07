# Values for the MeteoSwiss map locations

This example generates daily UV values for 20 towns and six mountain regions,
using the package's daily-product calculation. It writes 36 entries per day,
72 for today and tomorrow, and prints a table of the rounded values.

The towns are Genf, Neuenburg, Lausanne, Sion, Bern, Freiburg, Delémont, Basel,
Aarau, Luzern, Zürich, Schaffhausen, St. Gallen, Vaduz, Glarus, Chur, Davos,
St. Moritz, Scuol and Locarno. Names and ordering follow the map catalog.

## Generate the values

Install the package and prepare `work/uv.nc` with the
[README workflow](../README.md#calculate-uv-fields). Use a grid covering all of
Switzerland and daylight on both days; the default download bounding box covers
the catalog. Choose the intended issuance on the ICON initialization date:

```sh
uv run --no-sync python examples/meteoswiss_map.py \
  --grid work/uv.nc \
  --issued-at "YYYY-MM-DDT06:00:00Z" \
  --output work/meteoswiss-map.json
```

Replace the date placeholder. When replaying saved inputs, use their original
issuance date so that source-age checks and local dates describe that forecast.
The script requires no network access once the UV grid is saved.

The same [catalog](../examples/meteoswiss_map_locations.json) works directly with
the package CLI, for example in a scheduled data-generation job:

```sh
uv run --no-sync icon-uv daily \
  --grid work/uv.nc --catalog examples/meteoswiss_map_locations.json \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/meteoswiss-map.json
```

Each output entry contains `location.id`, `location.label`, `valid_date`, raw
`uvi`, rounded `display_uvi`, `category`, `status` and selection details. Join
map markers by the stable location ID; regional IDs also include the elevation,
such as `walliser_alpen_2000`. Use `display_uvi` for the number and `category` for
its colour. An unavailable value stays `null` and prints as `—`; its `reasons`
explain missing support or coverage. See the [daily-product reference](daily-products.md)
for category thresholds, rounding and quality states.

## Geographic choices

Town coordinates are settlement reference points from the
[swisstopo location search](https://docs.geo.admin.ch/access-data/search.html).
Elevations come from its [height service](https://docs.geo.admin.ch/access-data/get-point-height.html)
at those points, rounded to metres. The catalog includes the source settlement
IDs. Davos uses Davos Platz. These are example target points for the named towns;
the map image does not specify exact forecast-point coordinates.

Regions use the following example boxes in WGS84 `[west, south, east, north]`:

| Region | Elevations (m) | Bounding box |
|---|---|---|
| Jura | 1000 | `[6.0, 46.5, 7.9, 47.55]` |
| Walliser Alpen | 1000, 2000, 3000 | `[7.0, 45.9, 8.4, 46.4]` |
| Berner Alpen | 1000, 2000, 3000 | `[7.3, 46.4, 8.4, 46.8]` |
| Glarner Alpen | 1000, 2000, 3000 | `[8.7, 46.7, 9.3, 47.0]` |
| Bündner Alpen | 1000, 2000, 3000 | `[9.3, 46.3, 10.5, 46.9]` |
| Tessiner Alpen | 1000, 2000, 3000 | `[8.4, 46.2, 9.1, 46.7]` |

Jura has one value at 1000 m; the 2000 and 3000 m levels are omitted. Boxes are
coarse geographic selections and can overlap neighbouring regions or extend
across national borders. They are configurable example boundaries.

Towns use the nearest native cell within 5 km and 300 m of the target elevation.
For each regional elevation, the exporter selects cells within ±200 m and
reports the 90th percentile of their daily peaks. It requires at least five
cells and complete daylight for at least 95% of them. Elevation entries use
actual model terrain at each level; no value is extrapolated to a nonexistent
Jura elevation. The [calculation method](method.md) describes the radiation
model used to generate these values.
