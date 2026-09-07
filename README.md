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

To run the current API and bundled examples, install from the repository with
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

Follow the [forecast workflow](https://ofuhrer.github.io/icon-uv/#calculate-uv-fields)
to download ICON/CAMS inputs, compute a saved UV grid and export location products.
The guide explains cycle selection, daylight coverage and ensemble options.

## Hourly and daily locations

Define a point with coordinates and elevation, or a regional elevation band.
The same catalog drives hourly point NetCDF and daily JSON; optional albedo and
terrain horizons describe a specific site. See the
[location API](https://ofuhrer.github.io/icon-uv/location-api/) for the Python API,
JSON catalog and command-line examples.

Daily products reconstruct a rolling 30-minute peak from saved cloud and
atmospheric state. They include ensemble summaries, support details and freshness
checks. The [offline example](https://github.com/ofuhrer/icon-uv/blob/main/examples/offline.py)
runs the complete saved-input workflow with synthetic data.

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
