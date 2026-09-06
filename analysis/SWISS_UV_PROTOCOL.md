# Swiss observational expansion protocol

Frozen before inspecting new UV magnitudes or model errors, 6 September 2026.
The existing 150 dates and both forecast days remain fixed. No model/table fit.

## PMOD/WRC via the Medical University Innsbruck network

Use the two sites identified as CH in the official sites API: Davos (46.80 N,
9.83 E, 1610 m) and Weissfluhjoch (46.83 N, 9.82 E, 2540 m). These are distinct
from the SMN coordinates and the older WOUDC Davos coordinates. Match each to
the nearest native ICON cell independently, retain distance and terrain height,
and evaluate geometry/pressure at the published instrument location/altitude.
Coordinates are only published to 0.01 degree, so retain that uncertainty.

The `uve` API explicitly specifies UV-Index. The publisher's uv-chart-tools.js
tooltip defines each timestamp as the centre of a ±15-minute interval. Evaluate
the unchanged radiative method with six five-minute midpoint samples in that
interval; no point-sample versus interval comparison. Retain all missingness.
The historical high-resolution endpoint was empty in the availability probe.
This feed has no sample QC or instrument serial/calibration history; results are
provisional observational evidence, not final calibrated-network certification.
Cross-check overlapping Davos windows against the independent WOUDC archive
where possible. Do not infer independent instruments from duplicate feeds.

Score both paired half-hour values and maxima on the common half-hour grid.
Require every geometric daylight window (midpoint zenith < 90 degrees) in the
03:00–21:00 UTC analysis day for a complete-day score. No interpolation across
missing observations. Also report central-sun windows (zenith <= 70 degrees)
to separate documented mountain-horizon effects. Half-hour-grid maxima are a
separate diagnostic from the product's five-minute rolling peak: compare both
on complete days and quantify the sampling difference explicitly.

Primary historical UV albedo stays 0.05; sensitivities 0.15 and 0.8 remain fixed.
The archive does not establish the production SNOWC input, so these are bounded
historical method tests, not exact operational replays. Report snow-depth strata
(zero, positive, missing), seasons, years, forecast day and weather where DWH
sunshine is available. Native and gray methods use identical samples. Nearby
DWH shortwave is an attribution diagnostic with explicit separation/altitude
metadata, not a claim of an exactly colocated pyranometer.

Use raw bias/MAE/RMSE, rounded-UVI agreement within one, risk-category agreement,
underprediction across category thresholds, and severe category underprediction.
Bootstrap dates, not individual windows; retain both sites/days in shared date
resamples, season-stratified circular blocks of three selected campaign dates
(roughly fifteen days), 2,000 replicates, seed 20260906. Report small strata and
zero-event limits without claiming zero future risk. Missing/failed days are in
the coverage denominator, never silently dropped from a readiness claim.

## Other Swiss sites

Inventory all SACRaM global erythemal streams and the distinct PMOD locations.
Probe DWH production, development and deployment, including known final one-
minute and older ten-minute parameters. Raw mV is not irradiance; UVClim is a
modelled product, not a reference. Catalogue entries alone do not establish data
availability. Keep Payerne's 84-date reservation unscored until its archived
observation adapter is qualified and frozen separately. Jungfraujoch and Locarno
are not counted as validated without actual qualified matched UV observations.

## Verification and record

Record HTTP/command status, bytes and SHA256; reuse only identical cached input.
Check site identity, UTC, units, duplicates, finite values, interval completeness,
native GRIB identity, forecast cycle/lead, and interpolation bounds. Independently
recompute selected model windows and all summaries; inspect source-feed agreement
without selecting a favourable correction. Preserve all older frozen campaigns.

Sources: https://uv-data.i-med.ac.at/public/sites/ ;
https://www.uv-index.at/assets/js/uv-chart-tools.js?v=1.0.0 ;
https://www.uv-index.at/about/ ;
https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/
