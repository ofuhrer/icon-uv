# Verification and validation

icon-uv has been checked against Swiss UV measurements and direct radiative-transfer
calculations. The results below summarize the evidence and its coverage, helping
users assess suitability for their locations and products.

## Swiss measurement comparisons

The observational assessment spans 150 ICON initialization dates across all four
seasons from August 2024 to August 2026. It includes 583 complete forecast
site-days at Davos, Weissfluhjoch and Payerne. Results use the CTRL member;
the first and second forecast days are scored separately.

MAE is mean absolute error in unrounded UVI. Each pair below gives the first /
second forecast day. Display agreement follows the package's
[rounding rules](daily-products.md#peak-rounding-and-categories).

| Site | Complete days | Daily-peak MAE (UVI) | Within one displayed unit |
|---|---:|---:|---:|
| Davos | 146 / 146 | 0.61 / 0.64 | 89% / 88% |
| Weissfluhjoch | 100 / 99 | 0.78 / 0.85 | 86% / 81% |
| Payerne | 46 / 46 | 0.48 / 0.50 | 98% / 94% |

The comparison uses matching half-hour observation and prediction windows, with
fixed UV albedo 0.05 because historical production snow fraction was unavailable.
Payerne's minute observations also support the exported 30-minute rolling peak,
with MAE about 0.52 UVI on both forecast days.

Forecast solar radiation and spatial matching account for an important part of
the error. Replacing forecast radiation with measurements reduces daily-peak MAE
at all three sites. Alternative grid matches change some mountain-site peaks by
more than one UVI unit. This reflects differences between native model terrain,
local cloud conditions and instrument locations.

## Cloud conversion and numerical accuracy

Cloud conversion was assessed separately from weather prediction by using
colocated measured shortwave radiation as input at Payerne. Across 290 cloudy
hours on 57 summer/autumn days, the method has **0.11 UVI MAE** and **+0.07 UVI
mean error** against measured UV. Here, cloudy means shortwave below 80% of the
modeled clear-sky value; solar zenith angles are at most 70° and clear-sky UVI is
at least 1. These are a subset of the existing campaign, using fixed albedo 0.05.

Direct libRadtran calculations test both numerical interpolation and physical
assumptions. Across 80 withheld atmospheric states, the 95th-percentile relative
error is 2.8% for forward UV interpolation and at most 1.7% for shortwave-to-UV
conversion, evaluated where reference UVI is at least 1. These measure numerical
accuracy within the selected solver physics.

A separate 150-case assessment varies cloud height, droplet size, phase and
surface reflectivity. Liquid-cloud height and droplet-size variants over a dark
surface remain within 0.14 UVI of the direct solver. Unresolved clear/cloudy
mixtures can produce differences around 0.5 UVI, while high ice clouds over
bright snow reach 1.3 UVI in the tested cases. These are sensitivities within
specified scenarios, not general error bounds. They identify limits of inferring
one effective liquid cloud from an hourly broadband radiation value.

The [method description](method.md) explains the cloud approximation, atmosphere,
surface assumptions and supported input ranges.

## Coverage and interpretation

- Measurement coverage varies by site and season. Payerne's January–June 2025
  records were excluded because instrument identity was missing; much of the
  Weissfluhjoch 2026 record was unavailable. Accessible corrected UV was not
  available for the identified Jungfraujoch and Locarno-Monti sites.
- The historical results do not directly validate production snow-dependent UV
  albedo or regional altitude-band aggregates. Extreme-UV observations and
  cloud-enhancement cases are sparse.
- Ensemble tests verify member handling, missing-data coverage and aggregation.
  The observation scores above describe CTRL performance; ensemble spread has
  not been calibrated against observations and excludes shared uncertainties in
  atmospheric composition and radiation physics.
- Comparisons with MeteoSwiss and DWD products help check magnitudes and identify
  differences in weather inputs, surface assumptions and regional aggregation.
  Agreement with another forecast is not a substitute for measurement validation.

## Run checks

The automated tests cover input units and intervals, radiation interpolation,
cloud inversion, direct-solver reference columns, missing members, daily products,
output encoding and file integrity. Saved-grid checks independently reconstruct
shortwave radiation from the inferred cloud state.

```sh
uv sync --locked --extra cams
uv run --no-sync pytest -q
uv run --no-sync python -m icon_uv.check_grid \
  --grid work/uv.nc --output work/grid_check.json
```

The final command requires a saved UV grid. Rebuilding and validating the radiation
table against a direct solver is described in [CONTRIBUTING.md](../CONTRIBUTING.md#change-the-radiation-table).

## Measurement and method sources

- Davos and Weissfluhjoch: [PMOD/WRC UV network](https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/),
  through the [Medical University of Innsbruck data service](https://uv-data.i-med.ac.at/public/sites/).
- Payerne: MeteoSwiss BSRN records through [PANGAEA](https://bsrn.awi.de/data/data-retrieval-via-pangaea/),
  including the [July 2025 UV record](https://doi.pangaea.de/10.1594/PANGAEA.992977).
- Radiative transfer: [libRadtran](https://www.libradtran.org/).
- Cloud-modification comparison: [Staiger et al. (2008)](https://acp.copernicus.org/articles/8/2493/2008/).
