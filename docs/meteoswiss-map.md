# UV forecast map example

Generate English UV forecasts for 30 towns and six mountain regions, then build
a single HTML page with day selection, zoom, pan and sun-protection guidance.
The page loads separate JSON files for locations, UV maps and swisstopo relief.
It bundles the map library and needs only a static HTTP server; no backend or
external map service is needed to view it.

## Open the included example

From the repository root, start a local server:

```sh
python -m http.server 8769 --bind 127.0.0.1
```

Open [the example map](http://127.0.0.1:8769/examples/map/index.html).
Keep the server running while viewing the page. Opening the HTML directly with
`file://` does not allow the browser to load the separate JSON files.

The included data contains a dated forecast snapshot for **7–10 September 2026**, with 184 location entries
from ICON 7 September 00 UTC and CAMS 6 September 12 UTC. The corresponding
[location JSON](../examples/map/index.locations.json) retains source times, hashes
and availability details; the field JSON contains all four pairs of gridded layers.
This is a fixed **CTRL** example, not an automatically refreshed page. New
downloads use the full ensemble by default.

Day selection updates the map. Labels are thinned when they would overlap,
giving the Valais and Grisons Alps and the main cities priority; zoom in to
reveal more locations. Zoom-out stops at the overview of Switzerland, and the
home control restores that view. Wheel and button zoom use short animated
transitions and respect the browser’s reduced-motion preference. Select a
marker for its unrounded UV Index and availability details. Small screens
also have a mountain-elevation table. The cog above Home opens map settings.

## Prepare a four-day forecast

Use a published 00 UTC ICON cycle with the **previous day's 12 UTC CAMS cycle**.
This avoids waiting for the matching 00 UTC CAMS forecast, typically available
around 10 UTC. The earlier CAMS cycle covers four complete daylight dates.
Follow the [installation instructions](../README.md#installation), then set both dates.
The default download includes all 21 members; add `--control` to `fetch-icon`
for a CTRL-only calculation:

```sh
ICON_REFERENCE="YYYY-MM-DDT00:00:00Z"
CAMS_REFERENCE="PREVIOUS-YYYY-MM-DDT12:00:00Z"
uv run --no-sync icon-uv fetch-icon \
  --reference "$ICON_REFERENCE" --first-lead 1 --last-lead 96 --output work/icon.nc
uv run --no-sync icon-uv fetch-cams \
  --reference "$CAMS_REFERENCE" --first-lead 12 --last-lead 108 --output work/cams.grib
```

Compute the full downloaded grid, using twelve solar samples per hour. Both the
location export and the field export below use this same grid:

```python
import xarray as xr
from icon_uv.data import load_cams, write_netcdf
from icon_uv.products import compute_grid

cams = load_cams("work/cams.grib")
with xr.open_dataset("work/icon.nc") as source:
    icon = source.load()
grid = compute_grid(icon, cams, samples=12)
write_netcdf(grid, "work/uv.nc")
```

## Generate JSON and HTML

Set issuance to the intended morning time on the ICON initialization date.
Replays use their original issuance, which controls local dates and source-age checks.

```sh
uv run --no-sync python examples/map/export_locations.py \
  --grid work/uv.nc --issued-at "YYYY-MM-DDT06:00:00Z" \
  --output work/meteoswiss-map.locations.json

uv run --no-sync python examples/map/export_fields.py \
  --grid work/uv.nc --issued-at "YYYY-MM-DDT06:00:00Z" \
  --output work/meteoswiss-map.fields.json

uv run --no-sync python examples/map/render.py \
  --input work/meteoswiss-map.locations.json --fields work/meteoswiss-map.fields.json \
  --output work/meteoswiss-map.html
```

With the local server above running, open
[the generated map](http://127.0.0.1:8769/work/meteoswiss-map.html).
The renderer writes four sibling files: `.html`, `.locations.json`, `.fields.json`
and `.basemap.json`. Keep these files together when copying or serving the map.
Omitting `--input` rebuilds the bundled example snapshot. Omit `--fields` with
a custom location JSON to build a location-only page.

Forecasts can be refreshed by replacing the location and field JSON files at
the same paths; the HTML stays unchanged. The page loads them afresh on reload.
Both the renderer and browser check that the products share the same grid hash,
issuance, radiation table, dates and peak definition. Publish matching location
and field files together. Edit `examples/map/template.html` and rerun
the renderer when changing the page itself.

The exporter produces four local dates (`daily-uv-v3` for ensembles, `daily-uv-v2` for CTRL), with 46 entries per day:
30 towns, three elevation bands for each of five Alpine regions, and one band
for Jura. Mountain bands appear in 3000 / 2000 / 1000 m order. The renderer also
limits longer input products to their first four dates. Partial daylight dates
remain unavailable rather than becoming partial daily maxima. `null` is shown
as `—`, distinct from zero. The [daily-product reference](daily-products.md)
defines rounding, categories, coverage rules and schema. The CLI equivalent is:

```sh
uv run --no-sync icon-uv daily --days 4 \
  --grid work/uv.nc --catalog examples/map/locations.json \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/meteoswiss-map.locations.json
```

The HTML renderer downloads relief tiles once to `work/swisstopo-relief-tiles/`;
`--cache PATH` chooses another cache. Reusing it allows offline rebuilding.
Use a new cache directory to refresh the basemap. Tiles are stored in the basemap JSON at zoom 9;
higher zoom magnifies that fixed resolution. The curated location, field and
basemap JSON files and HTML are checked in; new forecasts and tile caches stay local under `work/`.

## Map layers

Open the **cog above Home** to toggle **Locations** and **Map** independently.
Both start enabled:
UV shading sits behind the location badges. Turn either layer off to view the
other alone, or turn both off to explore the terrain relief. The **Map values**
selector switches between **Forecast** and **Clear sky**, keeping that choice
when the map layer is hidden. Location badges always show the forecast with clouds;
this is stated below the map when combined with clear-sky shading.

Both gridded products show the maximum reconstructed 30-minute mean over the selected
local day, matching the temporal definition of the location product. Clear sky
removes cloud optical depth and cloud scaling while retaining ozone, aerosol,
pressure and surface albedo. Select a field position to inspect its UV Index;
the **Map opacity** control in settings adjusts the strength of the colour
from 0 to 100%, starting at **100%**. The colours use
multiplicative blending over a contrast-enhanced relief, preserving ridges and
valleys even when the UV shading is prominent. Relief brightness indicates terrain
shading; the UV category is carried by the colour.

Fields use native model terrain and an open horizon. They do not represent a
fixed altitude or the regional 90th-percentile elevation-band values. Each map
pixel takes the geographically nearest native cell within 3 km; gaps remain
transparent. Town markers additionally match terrain height, so they can use a
different cell. The map clips the overlay to the swisstopo relief footprint.

The [field JSON](../examples/map/index.fields.json) embeds numerical PNG
rasters on a Web Mercator display grid, 360 pixels wide by default. Their red
and green bytes encode UV Index truncated to 0.01; alpha distinguishes missing
values from zero. This preserves the rounded category boundaries. Display
resampling adds no physical resolution. The browser decodes the values and
applies the same category colours as the markers; missing pixels remain clear.
No new Python dependencies or online map services are needed to view the page.

## Ensemble information

The default download includes all 21 ICON members. Each member is converted to
UV independently, followed by its daily peak and regional spatial aggregation.
The displayed value is the ensemble median; location popups also show P10–P90.
Gridded shading uses the median of native-cell member daily peaks. The footer
identifies the member count and deterministic quantile, or CTRL for a single
member input. Location and field popups report the contributing member count.
At least 19 of 21 complete member products are needed by default. The saved
September snapshot remains a CTRL example.

Both export scripts accept `--ensemble-quantile`, defaulting to `0.5`. Use the
same value for locations and fields: the renderer and browser reject mismatched
ensemble definitions. `fetch-icon --control` selects CTRL-only input; downstream
commands detect it automatically. See [ensemble products](daily-products.md#ensemble-products)
for schema details and the interpretation of uncertainty.

## Locations and regions

The [catalog](../examples/map/locations.json) contains Geneva,
Neuchâtel, Lausanne, Sion, Bern, Fribourg, Delémont, Basel, Aarau, Lucerne,
Zurich, Schaffhausen, St. Gallen, Vaduz, Glarus, Chur, Davos, St. Moritz,
Scuol, Locarno, Interlaken, Grindelwald, Zermatt, Brig, Andermatt, Engelberg,
Lugano, Bellinzona, Appenzell and La Chaux-de-Fonds. IDs remain stable independently
of the English display names.

The added towns cover the Bernese Oberland, Upper Valais, central Alpine valleys,
Ticino, Appenzell and the higher Jura. The six regional elevation-band summaries
provide the broader mountain context. Individual summits would need explicit
point-elevation and horizon treatment. In the bundled snapshot, Zermatt has no
native cell within the existing 5 km / 300 m matching limits and is unavailable.

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
Leaflet 1.9.4 is vendored with its [BSD 2-Clause license](../examples/map/vendor/leaflet-LICENSE)
and embedded in the generated page. Basemap attribution is displayed on the map.
