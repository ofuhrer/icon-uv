# Swiss measurement-site validation — 6 September 2026

The broader validation goal is complete for the observations accessible through
the authorized DWH client on Balfrin and primary public archives. Five distinct
Swiss UV locations were identified; three support provisional comparisons.
This advances the evidence for internal map-product development, while leaving
important Alpine, southern-Swiss and seasonal gaps.

The fixed 150-date ICON campaign spans August 2024–August 2026 and both forecast
days. It yields **583 complete site-days** out of 900 planned comparisons at the
three scored sites. Instruments and colocated feeds are not counted as extra
locations. No candidate fitting or production physics change was made.

| Location | Complete days, forecast day 1 / 2 | Daily-peak MAE, UVI | Within one displayed unit | Same category |
|---|---:|---:|---:|---:|
| Davos | 146 / 146 | 0.613 / 0.635 | 89.0% / 88.4% | 76.0% / 80.8% |
| Weissfluhjoch | 100 / 99 | 0.777 / 0.854 | 86.0% / 80.8% | 76.0% / 72.7% |
| Payerne | 46 / 46 | 0.484 / 0.502 | 97.8% / 93.5% | 89.1% / 87.0% |
| Jungfraujoch | 0 / 0 | Unavailable corrected UV | — | — |
| Locarno-Monti | 0 / 0 | Unavailable corrected UV | — | — |

These are matched half-hour-grid daily maxima under fixed UV albedo 0.05.
The historical archive lacks the production snow-fraction diagnostic, so they
are not an exact replay of the production snow treatment. Payerne's independently
reconstructed five-minute rolling 30-minute peak gives MAE 0.523 / 0.521 UVI,
within-one agreement 95.7% / 89.1%, and category agreement 84.8% / 78.3%.
PMOD's half-hour feed cannot directly validate this finer rolling support.

## What the measurements establish

Replacing forecast shortwave with observations reduces daily MAE by 0.268–0.338
UVI at Davos, 0.171–0.301 at Weissfluhjoch, and 0.269–0.309 at Payerne on paired
dates. All six season-stratified date-block 95% intervals exclude zero. Payerne
uses colocated BSRN shortwave; the mountain sites use nearby DWH stations.
Cloud/shortwave inputs are therefore a useful improvement priority, although
remaining errors also include snow, terrain, spatial support and observations.

The predeclared alternative station-to-grid matches change individual daily
peaks by up to 2.112 UVI at Davos and 1.084 at Weissfluhjoch. Davos day-one
categories change in 14.4% of cases. This makes surveyed instrument coordinates
and terrain representativeness more urgent than very small numerical refinements.
No alternative was selected from its error score.

The provisional primary experiment still underestimates by at least two
categories on 2/292 Davos and 4/199 Weissfluhjoch site-days. Payerne has 0/92,
which is not evidence of zero future risk. Only two observed Weissfluhjoch
site-days reach the displayed extreme category. Regional altitude-band products
and extreme-UV performance remain unqualified.

## Coverage and access limits

- DWH catalog and bounded national probes found four SACRaM raw global UV
  streams. All 150 campaign requests returned no corrected UV or its QC values.
  Raw mV cannot substitute for calibrated, ozone/SZA-corrected erythemal UVI.
- Davos and Weissfluhjoch use PMOD/WRC data distributed by Medical University
  Innsbruck. Units/time support are documented; complete instrument history and
  sample QC are absent. Weissfluhjoch has only five available campaign windows
  in 2026. Davos/WOUDC feed agreement is a consistency check, not an independent
  site replication.
- Payerne uses Laurent Vuilleumier/MeteoSwiss BSRN/PANGAEA measurements from the
  preserved 84-date reservation. Named-instrument months are accepted;
  January–June 2025 is excluded for missing instrument identity. There is no
  accepted Payerne spring comparison. Minute timestamp phase bounds change the
  daily peak by at most 0.085 UVI; 2/92 displayed integers are phase-ambiguous.
- Snow and sunshine strata remain explicit. The primary automatic snow-depth
  series is absent at Weissfluhjoch; it is not silently inferred from season.

## Next steps for reliable products

1. Obtain calibrated SACRaM records for Jungfraujoch and Locarno-Monti, Payerne's
   missing instrument history and missing Weissfluhjoch periods.
2. Resolve surveyed UV coordinates, height, timestamp support and calibration/QC
   metadata, then replay the frozen evaluation.
3. Validate actual production snow-fraction inputs and improve cloud/shortwave
   and spatial-support treatment. Keep subsequent fitting separate from held-out
   assessment; do not choose a universal snow albedo from these outcomes.
4. Run a prospective, season-spanning product replay with the existing coverage,
   category and severe-underestimation checks before operational qualification.

## Reproduction and verification

Detailed results, source citations, interval estimates, coverage figures and
exclusion records are in
[the generated report](../work/swiss-uv-sites-20260906/results/report.md).
The acquisition/analysis plans are [the goal](SWISS_UV_VALIDATION_GOAL.md),
[Swiss protocol](SWISS_UV_PROTOCOL.md),
[Payerne protocol](PAYERNE_EXPLORATORY_PROTOCOL.md) and
[spatial sensitivity protocol](SWISS_SPATIAL_SENSITIVITY.md).

From the repository root, with the analysis environment installed:

```sh
PYTHONPATH=. python analysis/swiss_uv_analysis.py --root work/swiss-uv-sites-20260906
PYTHONPATH=. python analysis/verify_swiss_uv.py --root work/swiss-uv-sites-20260906
PYTHONPATH=. python analysis/swiss_spatial_sensitivity.py --root work/swiss-uv-sites-20260906
PYTHONPATH=. python analysis/report_swiss_uv.py --root work/swiss-uv-sites-20260906
```

Independent checks passed for 14,129 unique observed half-hour windows, all
92 Payerne rolling peaks, 3,462 accepted daily method rows, 6,516 summary values
and 85,950 native values overlapping the earlier extraction. Full-field decode
checks passed for another 95 values spanning all four archive configurations.
The full run reproduces all 3,672 daily rows and 68,217 paired windows from the
pre-2026 subset exactly. All 110 repository tests pass; the existing netCDF4/NumPy
binary-size warning remains, with round-trip tests passing.

The analysis summary initially lacked a window `year` label. Deriving it from
the existing valid date repaired summary generation without changing observations
or predictions. A slow 2026 CAMS bulk request was replaced by monthly requests
for the same variables, region, cycles and leads. Historical freeze manifests
remain intact; `final_identity.json` records final code, input and result hashes.
