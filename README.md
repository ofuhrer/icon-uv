# icon-uv

[![CI](https://github.com/ofuhrer/icon-uv/actions/workflows/tests.yml/badge.svg)](https://github.com/ofuhrer/icon-uv/actions/workflows/tests.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://ofuhrer.github.io/icon-uv/)
[![PyPI](https://img.shields.io/pypi/v/icon-uv)](https://pypi.org/project/icon-uv/)
[![GitHub release](https://img.shields.io/github/v/release/ofuhrer/icon-uv)](https://github.com/ofuhrer/icon-uv/releases/latest)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/ofuhrer/icon-uv/blob/main/pyproject.toml)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue)](https://github.com/ofuhrer/icon-uv/blob/main/LICENSE)

**Calculate the UV Index from ICON weather forecasts and CAMS atmospheric
composition.** icon-uv provides hourly grid and point forecasts and daily JSON
for towns and mountain regions, using a bundled radiation lookup table.

Point forecasts need only coordinates and elevation. They use nearby ICON cloud
and snow conditions, with optional UV albedo and horizon overrides for a specific
site. Hourly and daily products share the same location definitions.

[![Animated Swiss UV forecast map](https://raw.githubusercontent.com/ofuhrer/icon-uv/main/docs/images/uv-map.gif)](https://ofuhrer.github.io/icon-uv/meteoswiss-map/)

## Installation

Install the released package with Python 3.11 or newer:

```sh
pip install 'icon-uv[cams]'
icon-uv --help
```

The API below requires **icon-uv 0.2.0 or later**. To run the bundled examples,
install from the repository with
[uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/ofuhrer/icon-uv.git
cd icon-uv
uv sync --locked --extra cams
```

The `cams` extra adds the ADS download client. CAMS requires an ADS account and
accepted dataset terms; follow the [CAMS API setup](https://ads.atmosphere.copernicus.eu/how-to-api).
ICON downloads are public. Omit `[cams]` when installing for saved inputs only.

## Try it without credentials

```sh
uv run --no-sync python examples/offline.py --output-dir work/offline
```

This creates **synthetic** ICON/CAMS inputs and writes hourly grid/point NetCDF
and daily JSON through the real radiation table. After installation it needs no
network or credentials. The output illustrates the formats, not a weather forecast.

## Calculate UV fields

Choose an available **00 UTC ICON cycle** and the **preceding day's 12 UTC CAMS
cycle**. Published ICON files have limited retention. Replace both date placeholders:

```sh
ICON_REFERENCE="YYYY-MM-DDT00:00:00Z"
CAMS_REFERENCE="PREVIOUS-YYYY-MM-DDT12:00:00Z"

uv run --no-sync icon-uv fetch-icon \
  --reference "$ICON_REFERENCE" --first-lead 1 --last-lead 48 \
  --output work/icon.nc
uv run --no-sync icon-uv fetch-cams \
  --reference "$CAMS_REFERENCE" --first-lead 12 --last-lead 60 \
  --output work/cams.nc
uv run --no-sync icon-uv run \
  --icon work/icon.nc --cams work/cams.nc --samples 12 --output work/uv.nc
```

ICON leads are interval boundaries: 1–48 produces 47 hourly intervals, covering
two Swiss daylight dates. `--bbox W S E N` selects a subset; the default covers
Switzerland and its surroundings. Keep the downloaded NetCDF inputs for offline
recalculation. Downloads use all 21 ICON members; add `--control` to `fetch-icon`
for CTRL only. Outputs retain member-specific cloud and surface conditions.

## One catalog for hourly and daily forecasts

```python
import xarray as xr
from icon_uv import (
    PointLocation, RegionBand, load_locations,
    compute_points, compute_daily, export_daily_file,
)

locations = load_locations([
    PointLocation("zermatt", 46.017536, 7.746568, 1617, label="Zermatt"),
    RegionBand("valais-3000", (7.0, 45.9, 8.4, 46.4), 3000),
])
with xr.open_dataset("work/uv.nc") as grid:
    hourly = compute_points(grid, locations.points)
    daily = compute_daily(grid, locations, dates=["2026-09-07", "2026-09-08"])

# Publish with the saved grid's hash and issuance freshness checks.
payload = export_daily_file(
    "work/uv.nc", locations, issued_at="2026-09-07T06:00:00Z",
    output="work/daily.json",
)
```

Use dates matching your saved forecast. Points calculate ambient horizontal UV at
the requested coordinates and elevation. UV albedo defaults to the selected
ICON cell's snow-derived estimate. Region bands report the spatial P90 of cell
daily peaks near their elevation; ensemble products then take the member median.
Daily peaks reconstruct a rolling 30-minute mean from the saved atmosphere and
cloud state, rather than taking a maximum of hourly means.

The same [JSON catalog](https://github.com/ofuhrer/icon-uv/blob/main/examples/shared_locations.json)
works with both commands:

```sh
uv run --no-sync icon-uv points --grid work/uv.nc \
  --locations examples/shared_locations.json --output work/points.nc
uv run --no-sync icon-uv daily --grid work/uv.nc \
  --locations examples/shared_locations.json --days 2 \
  --issued-at "YYYY-MM-DDT06:00:00Z" --output work/daily.json
```

See the [location API](https://ofuhrer.github.io/icon-uv/location-api/) for optional
site inputs, native-cell treatment and compatibility. The
[Davos example](https://github.com/ofuhrer/icon-uv/blob/main/examples/davos.json)
shows one supplied terrain horizon and assumed local UV albedo. No horizon
preprocessing or HORAYZON installation is required.

## Documentation and examples

- [Daily products](https://ofuhrer.github.io/icon-uv/daily-products/): peak definition,
  ensemble uncertainty, missing data and JSON schemas.
- [Output reference](https://ofuhrer.github.io/icon-uv/outputs/): NetCDF variables,
  provenance and quality flags.
- [Interactive map](https://ofuhrer.github.io/icon-uv/meteoswiss-map/): 30 towns and
  six mountain regions, with a dated CTRL snapshot and export scripts.
- [Calculation method](https://ofuhrer.github.io/icon-uv/method/) and
  [validation](https://ofuhrer.github.io/icon-uv/validation/): physics, evidence and limits.
- [Examples](https://github.com/ofuhrer/icon-uv/blob/main/examples/README.md),
  [development](https://github.com/ofuhrer/icon-uv/blob/main/CONTRIBUTING.md) and
  [releasing](https://ofuhrer.github.io/icon-uv/releasing/).

## Scope and limitations

The cloud fit uses ICON's downward shortwave flux **without orographic shading**
(`ASOD_S`). Ambient forecasts do not apply a local terrain horizon. A town marker
is an elevation-adjusted reference point; regional elevation bands provide context
for surrounding mountains and cable-car trips. One marker cannot represent every
slope, snow condition or cloud layer in a resort.

Snow-derived UV albedo is an experimental approximation. Cloud state is hourly;
subhourly products follow solar geometry and do not resolve rapid cloud changes.
Point elevation adjustments retain the source cloud column. Fixed atmospheric
profiles, plane-parallel radiation and approximate optional horizon screening
also limit accuracy; see the method and validation guides before interpreting results.

## Sources and license

- [MeteoSwiss ICON OGD](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model)
- [CAMS atmospheric composition forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts), produced by ECMWF for Copernicus
- [libRadtran](https://www.libradtran.org/), used to generate the radiation table
- [swisstopo elevation profiles](https://api3.geo.admin.ch/rest/services/profile.json), used for the supplied Davos horizon

Licensed under [BSD 3-Clause](https://github.com/ofuhrer/icon-uv/blob/main/LICENSE).
Input datasets and dependencies retain their own licenses and attribution requirements.
