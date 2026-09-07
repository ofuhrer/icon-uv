# UV forecast map example

Generate English UV forecasts for 20 towns and six mountain regions, then build
a single HTML page with day selection, zoom, pan and sun-protection guidance.
The page embeds the forecast, map library and swisstopo relief tiles, so it opens
directly from disk and works offline.

## Prepare the forecast

[ICON-CH2-EPS provides 120 forecast hours](https://opendatadocs.meteoswiss.ch/e-forecast-data).
For five full daylight dates, choose a published 00 UTC ICON cycle and the same
00 UTC CAMS cycle. Follow the [installation instructions](../README.md#installation),
then replace the date below:

```sh
REFERENCE="YYYY-MM-DDT00:00:00Z"
uv run --no-sync icon-uv fetch-icon \
  --reference "$REFERENCE" --first-lead 1 --last-lead 120 --output work/icon.nc
uv run --no-sync icon-uv fetch-cams \
  --reference "$REFERENCE" --first-lead 0 --last-lead 120 --output work/cams.grib
uv run --no-sync icon-uv run \
  --icon work/icon.nc --cams work/cams.grib --output work/uv.nc
```

CAMS also covers [five days](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts),
but its publication can lag ICON. Select a cycle published by both providers;
the public ICON archive has limited retention. The previous day's 12 UTC CAMS
run ends twelve hours earlier than the matching 00 UTC run and cannot cover the
entire ICON range. The grid calculation requires CAMS to bracket every interval
midpoint and does not extrapolate composition beyond its forecast.

To use an earlier CAMS cycle while retaining all available hours, replace the
`run` command with this explicit coverage selection. It also computes only the
native cells needed by the catalog and uses twelve solar samples per hour:

```python
import json
from pathlib import Path
import numpy as np
import xarray as xr
from icon_uv.data import load_cams, write_netcdf
from icon_uv.daily import select_support
from icon_uv.products import compute_grid

catalog = json.loads(Path("examples/meteoswiss_map_locations.json").read_text())
cams = load_cams("work/cams.grib")
with xr.open_dataset("work/icon.nc") as source:
    cells = np.unique(np.concatenate([select_support(source, e) for e in catalog["entries"]]))
    covered = (source.time >= cams.time.min()) & (source.time <= cams.time.max())
    icon = source.isel(cell=cells, time=np.flatnonzero(covered.values)).load()
grid = compute_grid(icon, cams, samples=12)
write_netcdf(grid, "work/uv.nc")
```

## Generate JSON and HTML

Set issuance to the intended time on the ICON initialization date. Replays use
their original issuance, which controls local dates and source-age checks.

```sh
uv run --no-sync python examples/meteoswiss_map.py \
  --grid work/uv.nc --issued-at "YYYY-MM-DDT10:00:00Z" \
  --output work/meteoswiss-map.json

uv run --no-sync python examples/render_meteoswiss_map.py \
  --input work/meteoswiss-map.json --output work/meteoswiss-map.html
```

Open `work/meteoswiss-map.html` in a browser. Each day has 36 values: 20 towns,
three elevation bands for each of five Alpine regions, and one band for Jura.
Five complete days produce 180 values. Day selection updates all markers;
mountain bands appear together in 3000 / 2000 / 1000 m order. Select a marker for
its unrounded UVI and availability details. Zoom in to reveal town labels on
small screens, where a separate table keeps all mountain elevations readable.
The home control restores the full view.

The exporter uses all supplied forecast daylight dates (`daily-uv-v2`), omitting
a trailing night-only date. Partial daylight dates stay visible with unavailable
values rather than partial daily maxima. `null` is shown as `—`, distinct from
zero. The [daily-product reference](daily-products.md) defines the rounding,
categories, coverage rules and schema. The CLI equivalent is:

```sh
uv run --no-sync icon-uv daily --days all \
  --grid work/uv.nc --catalog examples/meteoswiss_map_locations.json \
  --issued-at "YYYY-MM-DDT10:00:00Z" --output work/meteoswiss-map.json
```

The HTML renderer downloads relief tiles once to `work/swisstopo-relief-tiles/`;
`--cache PATH` chooses another cache. Reusing it allows offline rebuilding.
Use a new cache directory to refresh the basemap. Tiles are embedded at zoom 9;
higher zoom magnifies that fixed resolution. Generated forecasts, pages and
tile caches remain local under `work/`.

## Locations and regions

The [catalog](../examples/meteoswiss_map_locations.json) contains Geneva,
Neuchâtel, Lausanne, Sion, Bern, Fribourg, Delémont, Basel, Aarau, Lucerne,
Zurich, Schaffhausen, St. Gallen, Vaduz, Glarus, Chur, Davos, St. Moritz,
Scuol and Locarno. IDs remain stable independently of the English display names.

Town coordinates are settlement reference points from the
[swisstopo location search](https://docs.geo.admin.ch/access-data/search.html).
Elevations come from its [height service](https://docs.geo.admin.ch/access-data/get-point-height.html),
rounded to metres. Davos uses Davos Platz. These are example target points;
the reference image does not specify exact forecast-point coordinates.

Regions use example WGS84 boxes `[west, south, east, north]`:

| Region | Elevations (m) | Bounding box |
|---|---|---|
| Jura | 1000 | `[6.0, 46.5, 7.9, 47.55]` |
| Valais Alps | 1000, 2000, 3000 | `[7.0, 45.9, 8.4, 46.4]` |
| Bernese Alps | 1000, 2000, 3000 | `[7.3, 46.4, 8.4, 46.8]` |
| Glarus Alps | 1000, 2000, 3000 | `[8.7, 46.7, 9.3, 47.0]` |
| Grisons Alps | 1000, 2000, 3000 | `[9.3, 46.3, 10.5, 46.9]` |
| Ticino Alps | 1000, 2000, 3000 | `[8.4, 46.2, 9.1, 46.7]` |

Boxes can overlap neighbouring regions or extend across national borders. Native
cells are selected within ±200 m of each elevation; the reported value is the
90th percentile of cell daily peaks. At least five cells and complete daylight
for at least 95% of them are required. Jura has only its 1000 m band.
`map_latitude` and `map_longitude` place regional labels; they do not change the
cells used in the calculation.

## Map sources

The grey relief uses swisstopo's
[Light Base Map terrain layer](https://api3.geo.admin.ch/rest/services/api/MapServer/ch.swisstopo.leichte-basiskarte_reliefschattierung/legend)
through its [WMTS service](https://docs.geo.admin.ch/visualize-data/wmts.html).
Leaflet 1.9.4 is vendored with its [BSD 2-Clause license](../examples/vendor/leaflet-LICENSE)
and embedded in the generated page. Basemap attribution is displayed on the map.
