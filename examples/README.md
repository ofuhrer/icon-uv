# Examples

Run the commands below from the repository root after following the
[installation guide](../README.md#installation). Write new outputs under `work/`.

| Example | Contents and use |
|---|---|
| [davos.json](davos.json) | One point with altitude, UV albedo and a terrain horizon, for `icon-uv poi --locations`. |
| [product_locations.json](product_locations.json) | Towns and regional elevation bands, for `icon-uv daily --catalog`. |
| [map/](map/) | An English, four-day Swiss UV map with saved example data, generation scripts and browser assets. |

## Point and daily forecasts

With a computed hourly UV grid:

```sh
uv run --no-sync icon-uv poi --grid work/uv.nc \
  --locations examples/davos.json --output work/davos.nc
```

For daily values, set issuance to the forecast's intended release time:

```sh
uv run --no-sync icon-uv daily --days 4 --grid work/uv.nc \
  --catalog examples/product_locations.json \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/daily.json
```

See [daily products](../docs/daily-products.md) for grid preparation and custom catalogs.

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
