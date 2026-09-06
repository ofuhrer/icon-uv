# Multi-year ICON case protocol

Fixed on 6 September 2026 before scoring the new sample. The earlier three-run
study remains unchanged. This extension targets **150 distinct ICON-CH2 control
initializations on 150 dates**, 50 times the earlier three initializations.

## Sampling and interpretation

Use 00 UTC on days 3, 8, 13, 18, 23 and 28 of every month from August 2024 through
August 2026. This gives 30 dates in 2024, 72 in 2025 and 48 in 2026. August 2024 is
the documented beginning of the consolidated archive. Retain missing dates in
the coverage ledger; never replace them after seeing errors. These are distinct
weather days, not a claim of statistical independence. Preserve the operational
configuration identifier and grid identity for each initialization.

Primary intervals are 08–16 UTC on the initialization day. Evaluate the same
window on day two separately to test longer leads. Station-hours, lead windows
and ensemble members do not increase the initialization count. Count only cases
with verified inputs and actual matched observations as evaluated.

## Weather and terrain coverage

Report scores by year, meteorological season, station altitude (<800 m,
800–1800 m, >=1800 m), observed hourly sunshine (0–5, >5–<50, 50–60 minutes),
and measured snow depth (0 cm, >0 cm, missing). Sunshine is a measured proxy,
not definitive cloud-type classification. Keep unknown regimes separate.
Report the number of distinct dates in every stratum, including empty strata;
calendar coverage alone does not establish weather-regime coverage.

If a key regime has fewer than ten distinct dates, flag insufficient evidence.
A later, separately labelled challenge set may use observed meteorology to
select additional snow, low-cloud, variable-cloud, dust or smoke events. Do not
select cases by UV errors or merge an oversampled challenge set into an overall
representative score. Dust/smoke cannot be identified reliably from AOD alone.

## Input and observation contracts

Use native archived ICON-CH2 control fields; verify GRIB initialization, member,
grid UUID, parameter identity, vertical surface, temporal units and bounds.
Reconstruct downward SW from ASWDIR_S + ASWDIFD_S, then difference forecast-start
means using GRIB packing tolerances. Bridge-check this route against the retained
September 2026 ASOD_S inputs. Do not substitute ensemble medians, shaded-surface
fields, reanalysis, COSMO or another ICON configuration for the control forecast.

The archive pilot contains pressure, broadband albedo and snow depth, but no
SNOWC. Snow depth is not snow fraction. Until the exact SNOWC diagnostic or an
archived equivalent is qualified, this campaign validates the ICON SW forcing;
it must not be described as 150 end-to-end UV forecast validations. Prescribed
UV-albedo scenarios, if computed later, must be labelled separately.

Match SwissMetNet hourly SW and sunshine at their UTC interval ends; retain DWH
quality categories and require category 4 (plausible) for primary SW scores.
Keep missing and rejected observations in the denominator/coverage ledger.
Use native nearest cells, station position metadata and a 10 km cutoff; document
orography differences and station relocations. The fixed station roster is the
135 SW stations used in the earlier regional analysis.

Historical UV needs calibrated erythemal irradiance/UVI, explicit integration
bounds, QC flag definitions and instrument metadata. A successful empty request
is not data. Preserve UV availability separately from the SW case count.
For later full UV replays, use historical CAMS ozone/AOD initialized no later
than ICON and within the existing 36 h age limit, plus documented dissemination
latency; do not substitute modern analyses. Out-of-table states are exclusions
to report, not values to clip.

## Scores and verification

Report bias, MAE and RMSE in W/m², both pooled and equal-weighted across case-day
means. Report paired lead differences only on identical station/valid-hour
observations. Year/season/configuration differences are descriptive and can be
confounded by weather; they are not causal evidence of an upgrade's effect.
Use date-level distributions; no iid station-hour confidence intervals. No fit
or bias correction on these cases. Freeze source hashes before scoring, retain
selected raw boundary values and independent scalar reconciliation, execute the
analysis notebook and export standalone figures. Record limitations alongside
every case count.

## Source checks

- MeteoSwiss OGD retains only 24 h: https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model
- Open-Meteo individual runs start April 2026 for non-ECMWF models:
  https://openmeteo.substack.com/p/single-runs-api . A 2025-06-15 ICON-CH2 request
  returned unavailable; 2026-06-15 succeeded. Its reprojected fields/derived
  pressure are not substituted into the native archive cohort.
- Native GRIB parameter identities/units: https://www.dwd.de/DWD/forschung/nwv/fepub/icon_database_main.pdf
- PeakWeather provides ICON-CH1 and lacks global SW/UV in its listed variables:
  https://huggingface.co/datasets/MeteoSwiss/PeakWeather . It is not a substitute.

Operational archive and DWH access details are retained in the local work
manifest, not embedded with credentials or internal documentation in this repo.
