# Examples

Run the commands below from the repository root after following the
[installation guide](../README.md#installation). Write new outputs under `work/`.

| Example | Contents and use |
|---|---|
| [offline.py](offline.py) | Credential-free synthetic saved-input calculation using the real radiation table; writes grid, point and daily outputs. |
| [shared_locations.json](shared_locations.json) | Ambient points with ICON-derived albedo and a region, accepted by `points` and `daily --locations`. |
| [davos.json](davos.json) | One site with assumed UV albedo and a supplied swisstopo horizon, for hourly or screened daily output. |
| [product_locations.json](product_locations.json) | Explicit native points near stations, with regional elevation bands. |
| [map/](map/) | An English, four-day Swiss UV map with saved example data, generation scripts and browser assets. |

## Point and daily forecasts

For a first calculation without downloads or credentials:

```sh
uv run --no-sync python examples/offline.py --output-dir work/offline
```

All inputs are explicitly **synthetic**; this demonstrates the workflow and
formats, not an actual forecast. It produces two days of hourly grid/point
NetCDF and daily JSON through the bundled radiation table. For shared location
definitions, see the [location API](../docs/location-api.md).

With a computed UV grid, use the same catalog for both products:

```sh
uv run --no-sync icon-uv points --grid work/uv.nc \
  --locations examples/shared_locations.json --output work/points.nc
uv run --no-sync icon-uv daily --days 4 --grid work/uv.nc \
  --locations examples/shared_locations.json \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/daily.json
```

Replace issuance with the intended release time of your forecast. See
[daily products](../docs/daily-products.md) for input coverage and peak definitions.
To try explicit site screening, use `examples/davos.json` with `points` or with
`daily --terrain-screened`. Davos albedo 0.05 is an assumption; its horizon is
terrain-derived, not instrument-site calibration data. No terrain preprocessing
or HORAYZON dependency is needed.

## View the map

```sh
python -m http.server 8769 --bind 127.0.0.1
```

Open [localhost:8769/examples/map/](http://127.0.0.1:8769/examples/map/).
The included CTRL snapshot covers **7–10 September 2026**. Keep the server running:
`index.html` loads separate JSON files and cannot be opened directly with `file://`.

Inside `map/`:

- `export_locations.py` exports daily values using the `locations.json` catalog.
- `export_fields.py` exports forecast and clear-sky UV rasters from the same grid.
- `render.py` builds the page from `template.html` and the bundled Leaflet `vendor/` assets.
- `index.html` and `index.{locations,fields,basemap}.json` form the ready-to-view example.

To rebuild the saved example into `work/`:

```sh
uv run --no-sync python examples/map/render.py --output work/meteoswiss-map.html
```

Then open [localhost:8769/work/meteoswiss-map.html](http://127.0.0.1:8769/work/meteoswiss-map.html).
The first rebuild downloads and caches swisstopo relief tiles. The
[map guide](../docs/meteoswiss-map.md) explains how to generate a new four-day
ensemble forecast and refresh its JSON files without rebuilding the page.
Downloads use all 21 members by default; add `--control` to `fetch-icon` for CTRL only.
