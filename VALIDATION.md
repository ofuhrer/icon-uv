# Validation results

This page summarizes numerical tests and comparisons with Swiss UV measurements.
The figures below describe the stated samples and averaging methods, providing
a basis for assessing the package for a particular location or product.

## Swiss UV measurements

The campaign samples 150 ICON initialization dates from August 2024 to August
2026. Comparisons use 583 complete site-days across Davos, Weissfluhjoch and
Payerne, with the two forecast days scored separately.

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
reach the extreme category. Payerne spring instrument metadata and much of
Weissfluhjoch's 2026 record are absent. Jungfraujoch and Locarno-Monti were
identified, but accessible corrected UV was unavailable for comparison.

The [detailed Swiss results](analysis/SWISS_UV_FINDINGS.md) include source
citations, exclusions, timestamp sensitivity and spatial-support checks.

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
profile/water groups. See [physical sensitivity results](analysis/PRODUCT_READINESS_ASSESSMENT.md).

## Performance and verification

A 38,718-cell, 24-hour calculation took approximately 52 seconds on the tested
Apple-silicon Mac. A two-day catalog replay using 1,781 cells produced 54 JSON
entries in approximately 17 seconds with 242 MiB peak resident memory. Both
measurements use saved local inputs and exclude network acquisition.

Tests cover input units and intervals, packing tolerance, radiation interpolation,
cloud inversion, missing data, local-day/DST handling, spatial support, rounding,
JSON/NetCDF output and failed writes. Independent data checks reconciled 14,129
observed UV windows, 92 Payerne rolling peaks and 85,950 native values against
separate readers. The test environment reports a netCDF4/NumPy binary-size import
warning; the numerical and round-trip checks pass.

## Run checks

```sh
uv sync --locked --extra cams --group analysis
uv run --no-sync pytest -q
uv run --no-sync python -m icon_uv.check_grid \
  --grid work/uv.nc --output work/grid_check.json
```

The final command requires a saved UV grid. Direct-solver checks additionally
need libRadtran; see [table rebuilding](CONTRIBUTING.md#change-the-radiation-table).
[Analysis tools](analysis/README.md) provide acquisition, scoring and replay
instructions for the measurement studies.
