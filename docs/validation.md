# Verification and validation

This page summarizes numerical tests and comparisons with Swiss UV measurements.
The figures below describe the stated samples and averaging methods, providing
a basis for assessing the package for a particular location or product.

## Swiss UV measurements

The campaign samples 150 ICON initialization dates from August 2024 to August
2026, using the 00 UTC cycle on days 3, 8, 13, 18, 23 and 28 of each month.
Dates were selected before scoring, spanning all four seasons. Comparisons use
583 complete site-days out of 900 planned across Davos, Weissfluhjoch and
Payerne, with the two forecast days scored separately.

MAE is mean absolute error in unrounded UVI. Display and category agreement use
the [daily-product rounding and category rules](daily-products.md#peak-rounding-and-categories).
Every pair of values below gives the first / second forecast day.

| Site | Complete days, first / second forecast day | Daily-peak MAE (UVI) | Within one displayed unit | Same category |
|---|---:|---:|---:|---:|
| Davos | 146 / 146 | 0.613 / 0.635 | 89.0% / 88.4% | 76.0% / 80.8% |
| Weissfluhjoch | 100 / 99 | 0.777 / 0.854 | 86.0% / 80.8% | 76.0% / 72.7% |
| Payerne | 46 / 46 | 0.484 / 0.502 | 97.8% / 93.5% | 89.1% / 87.0% |

These peaks use matched half-hour windows and fixed UV albedo 0.05 because the
historical archive lacks production snow fraction. Payerne minute observations
also support the exported 30-minute rolling peak on five-minute window starts:
MAE is 0.523 / 0.521 UVI. The mountain feed provides half-hour values only.

On paired dates, replacing forecast shortwave with measured shortwave reduces
MAE by 0.268–0.338 UVI at Davos, 0.171–0.301 at Weissfluhjoch and 0.269–0.309 at
Payerne. All six date-block 95% intervals exclude zero. Payerne uses colocated
shortwave measurements; the mountain sites use nearby stations.

Alternative station-to-grid matches change individual peaks by up to 2.112 UVI
at Davos and 1.084 at Weissfluhjoch. These differences reflect the spatial
representativeness of model terrain, clouds and instrument locations.

Underestimation by at least two displayed categories occurs on 2/292 Davos and
4/199 Weissfluhjoch site-days, and 0/92 at Payerne. Only two observed site-days
reach the extreme category. These site comparisons do not directly test regional
altitude-band aggregates. Much of Weissfluhjoch's 2026 record is absent.
Jungfraujoch and Locarno-Monti were
identified, but accessible corrected UV was unavailable for comparison.

Davos and Weissfluhjoch measurements come from the [PMOD/WRC UV network](https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/)
via the [Medical University of Innsbruck data service](https://uv-data.i-med.ac.at/public/sites/).
Payerne measurements are from MeteoSwiss's BSRN records distributed through
[PANGAEA](https://bsrn.awi.de/data/data-retrieval-via-pangaea/), including the
[July 2025 UV record](https://doi.pangaea.de/10.1594/PANGAEA.992977).
Payerne records from January–June 2025 were excluded because instrument identity
was missing. A ±30-second observation-timing sensitivity check changed Payerne
peaks by at most 0.085 UVI; two of 92 displayed values depended on this timing.
Coverage and available quality metadata differ between feeds.

## Shortwave input checks

The same 150 initialization dates provide 159,630 matched station-hours at 135
SwissMetNet sites in the 08–16 UTC initialization-day window. Mean forecast bias
is +18.51 W/m², MAE 85.81 W/m² and root-mean-square error 127.12 W/m². Scores use
DWH quality-category-4 observations. Low, intermediate and high observed sunshine
durations are represented on 145, 150 and 145 dates respectively; these are
sunshine strata rather than cloud-type classifications. Station-hours share
weather systems and are not independent samples.

## Numerical accuracy

The lookup table is compared with direct libRadtran calculations at 80 withheld
atmospheric states. Relative errors below use the 57 states with reference
UVI at least 1; the largest forward absolute error across all 80 is 0.248 UVI.

| Calculation | 95th-percentile absolute relative error | Maximum |
|---|---:|---:|
| Forward interpolation | 2.76% | 3.21% |
| SW inversion with equal SW/UV albedo | 1.12% | 1.43% |
| SW inversion with different SW/UV albedos | 1.66% | 1.97% |

These compare interpolation with the selected solver physics. An additional
72-state study varies seasonal profile, water vapour, elevation, albedo and
cloud state. Conversion MAE ranges from 0.064 to 0.187 UVI across its three
profile/water groups, with maximum errors from 0.148 to 0.523 UVI. These
sensitivities describe changes to the reference atmosphere, separate from the
interpolation errors above.

## Performance and verification

A 38,718-cell, 24-hour calculation took approximately 52 seconds on the tested
Apple-silicon Mac. A two-day catalog replay using 1,781 cells produced 54 JSON
entries in approximately 17 seconds with 242 MiB peak resident memory. Both
measurements use saved local inputs and exclude network acquisition.

Tests cover input units and intervals, packing tolerance, radiation interpolation,
cloud inversion, missing data, local-day/DST handling, spatial support, rounding,
JSON/NetCDF output and failed writes. Independent data checks reconciled 14,129
observed UV windows, 92 Payerne rolling peaks and 85,950 native values against
separate readers. Saved-grid checks also compared native-cell decoding and
daily JSON values with independently reconstructed results.

## Run checks

```sh
uv sync --locked --extra cams
uv run --no-sync pytest -q
uv run --no-sync python -m icon_uv.check_grid \
  --grid work/uv.nc --output work/grid_check.json
```

The final command requires a saved UV grid. Direct-solver checks additionally
need libRadtran; see [table rebuilding](../CONTRIBUTING.md#change-the-radiation-table).
