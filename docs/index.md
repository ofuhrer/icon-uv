# icon-uv

**Calculate the UV Index from ICON weather forecasts and CAMS atmospheric
composition.** icon-uv provides a Python API and command-line tools for hourly
grid and point forecasts, plus daily JSON products for towns and mountain regions.
Point and daily products share one location catalog: coordinates and elevation
are enough, with ICON-derived albedo and ambient horizontal UV by default.
Calculations run locally using a bundled radiation lookup table.

[![Animated Swiss UV forecast map](images/uv-map.gif)](meteoswiss-map.md)

## Installation

Install from PyPI with Python 3.11 or newer:

```sh
pip install 'icon-uv[cams]'
icon-uv --help
```

The `cams` extra adds the ADS download client. Omit it when working only with
saved inputs. CAMS downloads require an ADS account and accepted dataset terms;
follow the [CAMS API setup instructions](https://ads.atmosphere.copernicus.eu/how-to-api).
ICON downloads use the public MeteoSwiss STAC service without an account.

## Try it without credentials

Clone the repository to get the example scripts, then use
[uv](https://docs.astral.sh/uv/) to install the locked dependencies:

```sh
git clone https://github.com/ofuhrer/icon-uv.git
cd icon-uv
uv sync --locked --extra cams
uv run --no-sync python examples/offline.py --output-dir work/offline
```

The example creates synthetic ICON/CAMS inputs, runs the bundled radiation
table, and writes hourly grid and point NetCDF and daily JSON. It needs no
network access or credentials after installation. Its September 2026 dates
illustrate the formats; the output is not a weather forecast.

For real forecasts, follow the
[download and calculation workflow](https://github.com/ofuhrer/icon-uv#calculate-uv-fields)
using an available ICON cycle and the preceding day's CAMS cycle.

## Choose a guide

| Task | Guide |
|---|---|
| Use one location catalog for hourly and daily products | [Location API](location-api.md) |
| Export daily peaks, categories and ensemble information | [Daily products](daily-products.md) |
| Read NetCDF variables and quality flags | [Output reference](outputs.md) |
| Build an interactive Swiss UV map | [Map example](meteoswiss-map.md) |
| Understand the model and its physical assumptions | [Calculation method](method.md) |
| Understand verification results and their limits | [Verification and validation](validation.md) |

Development instructions are in
[CONTRIBUTING.md](https://github.com/ofuhrer/icon-uv/blob/main/CONTRIBUTING.md).
See [Releasing](releasing.md) for package publishing. Report problems through
[GitHub issues](https://github.com/ofuhrer/icon-uv/issues).

This site tracks `main`. The shared location defaults require icon-uv 0.2.0 or
later. Version-specific source and
documentation are available in [GitHub releases](https://github.com/ofuhrer/icon-uv/releases).
