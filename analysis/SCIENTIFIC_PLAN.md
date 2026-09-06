# Scientific hardening protocol

This protocol is fixed before examining the expanded evaluation results on
6 September 2026. It is a prospective protocol for this extension, not a claim
that the original 5 September case was unseen. No parameters will be fitted.

1. **Forecast evaluation:** retrieve the available 5 September 00, 06 and 12 UTC
   ICON-CH2 control cycles, expanding the geographic bounds to cover public UV
   network sites where native model cells exist. Use one common CAMS composition
   cycle (4 September 12 UTC) to isolate changes in ICON forcing/state. Report
   this limitation; do not label the comparison a full operational-cycle test.
2. **Primary scores:** fixed 08–16 UTC for the 00 UTC forecast, irrespective of
   observed UV magnitude. Retain the previous observed-UVI ≥1 cohort only as a
   secondary diagnostic. Report exclusions and completeness for every site.
3. **Cycle comparison:** match site and valid interval across cycles before
   calculating paired differences in absolute errors. Give each cycle the exact
   same observations and weights. Daytime windows unavailable to a later cycle
   are excluded from both sides, not filled or scored as zero.
4. **Historical conversion experiment:** 29 August–5 September at Davos and
   Weissfluhjoch, using nearby measured shortwave and surface pressure, daily
   CAMS composition, and explicit surface-albedo assumptions. This evaluates an
   observation-driven radiation conversion; it is not historical ICON skill.
   Describe non-colocation and pressure-height correction. Preserve per-day
   scores and stratify using measured sunshine, not observed UVI errors.
5. **Robustness:** compare the radiative-transfer cloud inversion against an
   unfitted gray-cloud baseline (clear UVI × measured/model SW divided by modeled
   clear SW). Test UV and SW albedo assumptions and solar temporal quadrature.
   Show missingness and model flags; do not silently drop problematic regimes.
6. **Uncertainty:** report site/day distributions and leave-one-day-out ranges.
   Do not treat individual station-hours as independent samples or attach an
   iid confidence interval. Eight days cannot establish seasonal skill. Albedo
   scenarios are sensitivity calculations, not calibrated uncertainty bounds.
7. **Reproducibility:** freeze input hashes before evaluation, verify them before
   every replay, store all analysis code in the repository, and record the code
   identity and software environment alongside the outputs. Do not regenerate
   an expected hash from an input inside its own validation check.
8. **Verification and delivery:** test timestamp, missing-data, matching and
   aggregation logic with analytically known examples; independently reconcile
   results from archived raw observations; execute the notebook; inspect plots;
   update the scientific assessment and document unavailable evidence.

The public ICON interface retains assets for 24 hours. The 4 September 00 UTC
query returned no assets during this investigation. Multi-day ICON verification
therefore needs a separately archived forecast collection; newer initializations
must not be substituted for historical issue times.

Sources: [MeteoSwiss ICON documentation](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model),
[SwissMetNet time conventions](https://opendatadocs.meteoswiss.ch/general/download),
[PMOD/WRC measurement sites](https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/).
