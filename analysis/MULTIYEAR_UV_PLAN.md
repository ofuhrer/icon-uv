# WOUDC UV extension (fixed before UV scoring)

The public WOUDC Broad-band archive contains PMOD/WRC Davos instrument 501A/1492
records for 2024–2025; a 2025 pilot file was successfully retrieved. Use this
fixed instrument at its reported station-501 coordinates (46.82°N, 9.85°E,
1590 m), retaining per-file metadata. Do not merge redundant instruments or
assume it is identical to the earlier live UV feed. Record missing files for all
150 dates, including 2026. Keep instrument/QC limitations explicit.

Integrate the high-frequency erythemal irradiance by piecewise-linear
trapezoids over each exact hourly interval, requiring bracketing samples and no
gap over the cadence-specific limit (30 s for nominal 10 s records; 75 s for
nominal 60 s records). Nominal cadence is the median sample spacing in
07:59–16:01 UTC; only 8–12 s or 55–65 s medians are accepted. Convert W/m² to UVI with factor 40. Record exclusion reasons;
do not fill long gaps or interpret absent per-sample QC as a passed QC flag.

Use native ICON SW, pressure and broadband albedo at the nearest source cell;
adjust pressure to the reported station altitude with the existing 8434 m scale
height and calculate at the station coordinates. Use previous-day 12 UTC CAMS
forecasts, at 3 h resolution covering both windows. The primary *diagnostic*
uses explicitly prescribed UV albedo 0.05; sensitivities use 0.15 and 0.80.
Compare to the unfitted gray-cloud baseline and stratify by nearby measured
snow. These are ICON-driven POI diagnostics under stated surface assumptions,
not reproduction of the production grid's missing SNOWC input. Do not count
these as fully qualified end-to-end UV forecasts. Native model SW validation,
UV diagnostic cases and fully reproduced production UV cases have separate
counts. No empirical fitting or operational accuracy claim.

A source-inspection revision before UV scoring replaced the initial universal
30 s gap limit: 37 otherwise complete files per lead window had regular 59–61 s
spacing. The 75 s limit admits this documented archive cadence while rejecting
a missing minute. This is a timing-contract correction, not selection by errors.
