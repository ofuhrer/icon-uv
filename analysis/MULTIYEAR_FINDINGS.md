# Multi-year ICON scientific evaluation

**150 ICON-CH2 control initializations on 150 dates, August 2024–August 2026:**
50 times the previous three initializations, spanning all four seasons and three
calendar years. Dates were fixed before scoring: days 3, 8, 13, 18, 23 and 28 of
each month. Source: MeteoSwiss.

The primary SW evaluation contains **159,630 matched station-hours**
at 135 stations. The following-day window is also evaluated separately. These
station-hours are correlated; they are not independent sample replicates.

WOUDC supplies sufficient Davos measurements for **67
initialization-day UV diagnostic cases** (22.3 times the
previous initialization count), with 533 matched hours. These use
explicit UV-albedo assumptions. They are not exact production-grid UV replays:
the native archive does not provide the required SNOWC field. The new count of
fully reproduced production UV cases is **zero**; the original three remain the
existing reference study.

[Local figure: Monthly case coverage](../work/scientific-multiyear-20260906/results/multiyear_coverage.png)

## Findings

- Primary SW bias is **+18.51 W/m²**, MAE **85.81 W/m²**,
  and RMSE **127.12 W/m²**. Equal-day bias/MAE are
  +18.52/85.78 W/m².
- The earlier weather-regime pattern persists over many dates: SW bias is
  +83.41 W/m² for 0–5 minutes of measured sunshine,
  +32.05 W/m² for intermediate sunshine,
  and -49.76 W/m² for 50–60 minutes.
  Those measured regimes occur on 145,
  150 and
  145 primary dates respectively.
  They are sunshine-based strata, not validated cloud-type classifications.
- SW bias varies seasonally: winter +29.04, spring
  +19.12, summer +4.04, autumn
  +24.33 W/m². Seasonal absolute errors and paired
  weather differences must not be confused with changes in model quality.
- Davos UV, with prescribed UV albedo 0.05: bias **+0.186 UVI**, MAE
  **0.533 UVI**; gray-cloud baseline MAE **0.527 UVI** on the same
  hours. The UV-albedo 0.80 scenario has bias +1.587 UVI. Surface
  scenarios are sensitivity experiments, not fitted corrections or uncertainty
  bounds. See the season/snow tables before interpreting the pooled scores.

| Season | SW dates | SW bias / MAE (W/m²) | UV dates | UV bias / MAE (UVI) |
|---|---:|---:|---:|---:|
| DJF | 36 | +29.04 / 61.43 | 18 | -0.109 / 0.133 |
| MAM | 36 | +19.12 / 99.80 | 18 | +0.369 / 0.726 |
| JJA | 42 | +4.04 / 107.82 | 20 | +0.249 / 0.846 |
| SON | 36 | +24.33 / 70.38 | 11 | +0.241 / 0.290 |

UV columns use the prescribed albedo 0.05 diagnostic at Davos; SW columns use
the 135-station network. Both are initialization-day windows. Absolute UV
errors depend strongly on the seasonal UVI range. The small pooled MAE
difference between the UV method and gray-cloud baseline does not establish
a reliable skill advantage for either method.

[Local figure: Seasonal and sunshine-stratified SW errors](../work/scientific-multiyear-20260906/results/multiyear_sw.png)

[Local figure: Davos UV diagnostics](../work/scientific-multiyear-20260906/results/multiyear_uv.png)

## Coverage and scientific limits

Every planned case has matched SW observations. The primary ledger retains
2,370 excluded station-hours, including missing
observations and changed station positions. Only DWH quality category 4 enters
primary SW scoring. Measured snow is present on 148 primary dates somewhere in
the network, but snow observations are missing for many station-hours; the snow
stratification is not a complete snow-cover validation.

There are 30 primary dates in 2024, 72 in 2025 and 48 in 2026; winter, spring,
summer and autumn contain 36, 36, 42 and 36 dates. Operational configuration
identifiers are retained per case (739: 26 dates, 740: 93 dates, 741: 27 dates, 742: 4 dates). The newest configuration
742 is represented by only four dates. This is not a seasonal qualification of
that latest configuration. Comparisons across configurations are
confounded by season/weather and are not causal upgrade assessments. Day-zero
and day-one windows sample different valid dates; their overall errors are
reported separately, not as a paired forecast-lead skill change.

WOUDC coverage is limited to one fixed Davos instrument in this extension,
with missing days explicitly retained. Instrument metadata, processing versions
and source timestamps are saved. The records do not carry per-sample QC flags;
archive inclusion does not establish full calibration/QC qualification. Hourly
means use bracketing high-frequency samples with cadence-specific gap limits (30 s for nominal 10 s records, 75 s for
nominal 60 s records). A missing minute is rejected.
Coordinates/height in the WOUDC metadata are coarse. Nearby SwissMetNet snow and
sunshine are not colocated UV-instrument measurements. Atmospheric composition
comes from historical previous-day 12 UTC CAMS forecasts; dissemination latency
is not reconstructed. The fixed summer atmospheric profile, cloud assumptions,
low-sun approximation and unknown effective UV albedo remain limitations.
The primary UV sample retains 64 low-sun flagged
hours and 84 hours using scaling above the modeled
clear-sky SW value; 7 hours have both flags. These approximations are
included in the stated scores, not silently discarded.

Dust/smoke and specific low-cloud or convective event types have not been
independently classified. A later event challenge set should be selected from
meteorological evidence, without choosing cases by UV errors. This campaign
broadens evidence substantially; it does not qualify an operational UV product.

## Verification and reproducibility

Frozen input manifests protect replay against changed downloaded inputs.
Independent arithmetic reconciled **324,000** SW rows
against saved native boundary values and raw DWH timestamps/measurements; the
maximum flux discrepancy was 0 W/m².
The archive reconstruction agrees with the retained ASOD_S case to within
0.227 W/m². The source hashes, interval semantics, member and grid identities
are retained. See `verification.json`, `uv_verification.json`, `run_identity.json`
and the executed notebook for the checks and their scope.
Independent integration of the raw WOUDC irradiances reconciled
1,068 hourly means to within
1.8e-15 UVI; independent scalar
arithmetic checked 192 UV summary values.

Repository tests: 77 passed, with the pre-existing NumPy/netCDF4 import warning.
Cluster extraction used installed ecCodes 2.36.4; the newer Python binding emits
a version recommendation. Numerical source/bridge checks pass; neither warning
is silently suppressed.

Replay instructions: [analysis/README.md](README.md).
Protocols: [SW](MULTIYEAR_PLAN.md) and
[UV](MULTIYEAR_UV_PLAN.md). No production model parameters were
fitted or changed for this expansion.

Sources: [MeteoSwiss ICON documentation](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model),
[DWD ICON GRIB parameter definitions](https://www.dwd.de/DWD/forschung/nwv/fepub/icon_database_main.pdf),
[WOUDC data access](https://www.woudc.org/en/data/data-access/),
[PMOD/WRC Davos records](https://woudc.org/archive/Archive-NewFormat/Broad-band_1.0_1/stn501/uv-biometer/).
