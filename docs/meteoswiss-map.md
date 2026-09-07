# UV forecast map example

Generate English UV forecasts for 20 towns and six mountain regions, then build
a single HTML page with day selection, zoom, pan and sun-protection guidance.
The page embeds the forecast, map library and swisstopo relief tiles, so it opens
directly from disk and works offline.

## Open the included example

Open [meteoswiss_map.html](../examples/meteoswiss_map.html) directly in a browser.
It contains a dated forecast snapshot for **7–10 September 2026**, with 144 values
from ICON 7 September 00 UTC and CAMS 6 September 12 UTC. The corresponding
[sample JSON](../examples/meteoswiss_map.sample.json) retains source times, hashes
and availability details. This is a fixed example, not an automatically refreshed page.

Day selection updates the map and the complete values list. Labels are thinned
when they would overlap, giving the main cities priority and revealing more
locations as you zoom in. Zoom-out stops at the overview of Switzerland; the
home control restores that view. Select a marker for its unrounded UV Index and
availability details. The expandable list keeps all towns and elevations accessible
at every zoom level. Small screens also have a mountain-elevation table.

## Prepare a four-day forecast

Use a published 00 UTC ICON cycle with the **previous day's 12 UTC CAMS cycle**.
This avoids waiting for the matching 00 UTC CAMS forecast, typically available
around 10 UTC. The earlier CAMS cycle covers four complete daylight dates.
Follow the [installation instructions](../README.md#installation), then set both dates:

```sh
ICON_REFERENCE="YYYY-MM-DDT00:00:00Z"
CAMS_REFERENCE="PREVIOUS-YYYY-MM-DDT12:00:00Z"
uv run --no-sync icon-uv fetch-icon \
  --reference "$ICON_REFERENCE" --first-lead 1 --last-lead 96 --output work/icon.nc
uv run --no-sync icon-uv fetch-cams \
  --reference "$CAMS_REFERENCE" --first-lead 12 --last-lead 108 --output work/cams.grib
```

Compute the native cells needed by the catalog, using twelve solar samples per hour:

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
    icon = source.isel(cell=cells).load()
grid = compute_grid(icon, cams, samples=12)
write_netcdf(grid, "work/uv.nc")
```

## Generate JSON and HTML

Set issuance to the intended morning time on the ICON initialization date.
Replays use their original issuance, which controls local dates and source-age checks.

```sh
uv run --no-sync python examples/meteoswiss_map.py \
  --grid work/uv.nc --issued-at "YYYY-MM-DDT06:00:00Z" \
  --output work/meteoswiss-map.json

uv run --no-sync python examples/render_meteoswiss_map.py \
  --input work/meteoswiss-map.json --output work/meteoswiss-map.html
```

Open `work/meteoswiss-map.html` in a browser. Omitting `--input` rebuilds the
bundled example snapshot. Edit `examples/meteoswiss_map.template.html` to change
the page layout; `examples/meteoswiss_map.html` is the ready-to-open generated page.

The exporter produces four local dates (`daily-uv-v2`), with 36 values per day:
20 towns, three elevation bands for each of five Alpine regions, and one band
for Jura. Mountain bands appear in 3000 / 2000 / 1000 m order. The renderer also
limits longer input products to their first four dates. Partial daylight dates
remain unavailable rather than becoming partial daily maxima. `null` is shown
as `—`, distinct from zero. The [daily-product reference](daily-products.md)
defines rounding, categories, coverage rules and schema. The CLI equivalent is:

```sh
uv run --no-sync icon-uv daily --days 4 \
  --grid work/uv.nc --catalog examples/meteoswiss_map_locations.json \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/meteoswiss-map.json
```

The HTML renderer downloads relief tiles once to `work/swisstopo-relief-tiles/`;
`--cache PATH` chooses another cache. Reusing it allows offline rebuilding.
Use a new cache directory to refresh the basemap. Tiles are embedded at zoom 9;
higher zoom magnifies that fixed resolution. The curated sample JSON and HTML
are checked in; new forecasts and tile caches stay local under `work/`.

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
