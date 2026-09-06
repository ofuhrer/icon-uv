# Expanded scientific validation of ICON UV

## Technical summary
The expanded evidence strengthens the adverse mountain finding and exposes a limitation of the current cloud inversion: a simple unfitted gray-cloud baseline has lower forecast MAE in this case. The analysis now covers 14 UV sites with complete primary-window observations, three ICON cycles, 135 shortwave stations, and a separate eight-day radiation-conversion experiment at two Swiss sites.

**Assessment: reproducible scientific case studies with explicit limitations; operational UV skill remains unvalidated.** The newer cycles are not uniformly better, and neither the cloud inversion nor a single bias correction can be justified from these cases. No parameters were fitted and the production forecast algorithm was not changed.

## Evaluation design and definitions
The evaluation protocol uses a fixed 08–16 UTC primary window, independent of observed UVI. The repository file `analysis/SCIENTIFIC_PLAN.md` was written before scoring the expanded results. The original four-site case was already known, so this extension is not presented as a completely unseen benchmark.

**Forecast evaluation:** 5 September 2026 ICON-CH2 control runs at 00, 06 and 12 UTC, with CAMS composition fixed to 4 September 12 UTC. Holding CAMS fixed isolates changes in ICON forcing/state; it is not a full operational forecast-cycle comparison or proof of issue-time data availability. Each UV site uses its nearest native cell within 10 km; all 20 listed sites are geometrically covered, at distances no greater than 1.46 km. Fourteen sites have eight usable UV pairs during 08–16 UTC. Bratislava, Dornbirn, Innsbruck, Leifers, Mariapfarr and Ritten have no usable pair in this window. They remain in the coverage tables with explicit exclusions.

**Historical experiment:** 29 August–5 September at Davos and Weissfluhjoch. Nearby measured global shortwave and surface pressure are combined with the previous day's 12 UTC CAMS composition. This is observation-driven radiation conversion, not historical ICON forecast skill. Reference shortwave/UV albedos are explicitly assumed to be 0.15/0.05; other surfaces are sensitivities, not inferred actual conditions.

Reported UV values at :15 and :45 are averaged to approximate an hourly mean. Their current averaging bounds and per-value QC remain unconfirmed. SwissMetNet timestamps are confirmed UTC interval ends. Positive bias means prediction minus observation. MAE and RMSE use paired hourly errors, with equal weight per retained pair. Relative mean excess is the ratio of sums minus one, not a mean of hourly percentages. Dose errors, where reported, refer only to the matched intervals, with 1 UVI-hour = 90 J/m² of erythemally weighted radiant exposure. No numerical pass/fail threshold was invented.

## Fourteen-site verification confirms large mountain errors
For the 00 UTC forecast, each usable site contributes eight hours. Mean UVI biases include **Sonnblick +3.02**, **Weissfluhjoch +1.95**, **Zugspitze +1.82**, **Davos +1.70**, and **Aosta +0.40**. Sonnblick's mean prediction is 5.27 versus 2.25 reported (+134%). All 14 site-mean biases are positive, although individual hourly errors can have either sign.

The current inversion's pooled MAE is **1.072 UVI**, versus **0.855 UVI** for the unfitted gray-cloud baseline on the same 112 pairs. The baseline multiplies modeled clear-sky UVI by incoming shortwave divided by modeled clear-sky shortwave. It uses identical atmospheric inputs and no observed UV calibration.

This comparison does not establish that gray attenuation is physically superior. It may compensate for excessive shortwave forcing, while the current inversion represents the spectral difference between broadband and erythemal attenuation. Added forecast skill from that inversion has not been demonstrated here. Any algorithm change should be evaluated on separate weather cases.

## Matching hours prevents a misleading cycle comparison
For 00 versus 06 UTC, 14 sites share 112 pairs over 08–16 UTC. Pooled MAE falls from **1.072 to 1.008 UVI**, a change of −0.064. Ten sites improve and four worsen. For 00 versus 12 UTC, the common support is only 13–16 UTC: 42 pairs. On those exact pairs, MAE rises from **0.585 to 0.667 UVI**, a change of +0.082. Four sites improve and ten worsen. Comparing the full 00 UTC window to the shorter 12 UTC window would incorrectly make the improvement appear much larger.

The corresponding shortwave comparison also shows small and inconsistent changes: MAE falls from 135.26 to 133.36 W/m² for 00 versus 06 UTC (1,080 identical pairs), but rises from 105.60 to 106.25 W/m² for 00 versus 12 UTC (405 identical afternoon pairs). These paired results describe this case, not a general lead-time dependence.

## Shortwave error changes sign with measured sunshine
The 00 UTC run retains the earlier regional bias of **+64.25 W/m²** across 135 stations and 1,080 hours. Stratifying by measured sunshine makes the aggregate more informative:

| Sunshine in an hour | Station-hours | Mean SW bias |
|---|---:|---:|
| 0–5 minutes | 427 | +150.19 W/m² |
| More than 5, less than 50 minutes | 454 | +38.26 W/m² |
| 50–60 minutes | 167 | −79.11 W/m² |
| Unknown sunshine | 32 | +34.35 W/m² |

Four stations lack sunshine metadata; their 32 hours remain in the radiation total but are not assigned a measured-sunshine regime. This pattern is consistent with errors in cloud amount or placement, but sunshine is a local radiation-derived proxy, not an independent map of cloud truth. Station-hours share the same weather situation and are correlated. A universal downward correction could worsen sunny-hour errors.

## Residual conversion errors persist across several days
In the historical experiment, all 128 requested daylight station-hours have shortwave/pressure drivers, but UV gaps leave **49/64 hours at Davos** and **37/64 at Weissfluhjoch**. Davos has data on seven days, six complete; Weissfluhjoch on five days, four complete. Missingness is substantial and is not treated as random.

| Site | Usable hours | RT bias | RT MAE | Gray-baseline MAE |
|---|---:|---:|---:|---:|
| Davos | 49 | +0.314 UVI | 0.355 UVI | 0.351 UVI |
| Weissfluhjoch | 37 | +0.622 UVI | 0.622 UVI | 0.534 UVI |

Relative mean excess is about 8.1% and 15.8%. Equal weighting of available daily mean errors gives +0.327 and +0.666 UVI. Leaving out each day with usable data yields mean-bias ranges of **+0.297 to +0.355** and **+0.533 to +0.699**. These are sensitivity ranges, not confidence intervals. Partial days are explicitly marked in the figure.

For hours with 0–5 minutes of sunshine, RT MAE is 0.196 UVI at Davos (seven pairs) and 0.324 at Weissfluhjoch (six pairs); the gray baseline gives 0.328 and 0.138. Neither method wins consistently across sites and regimes. These small subgroups support diagnosis, not method selection.

## Numerical and scientific robustness
Increasing solar samples from four to twelve changes the reconstructed site forecasts by at most **0.00213 UVI** across the three cycles. Thus solar quadrature is much smaller than the observed errors in this evaluation; that does not test within-hour cloud evolution or certify true subhourly maxima.

The historical reference calculation uses measured QFE pressure converted from hPa to Pa, then adjusted from barometer height to published UV height with a fixed 8,434 m scale height. This differs deliberately from the earlier same-cell shortwave substitution. Scores from the two experiments should not be mixed because surface state and primary cohorts differ.

Dark-surface assumptions (SW/UV albedos 0.05/0) give mean errors +0.287 and +0.596 UVI; a brighter-soil scenario (0.30/0.15) gives +0.393 and +0.704. A snow scenario (0.60/0.80) greatly increases UVI and is not evidence that snow was present. No albedo was chosen by optimizing agreement. Composition is from CAMS, not an independent ozone/aerosol measurement.

Measured SW exceeds the modeled reference clear-sky SW in 16 usable hours at each Swiss site. The existing above-clear scaling flag is retained and reported; maximum measured/model-clear ratios are 1.131 at Davos and 1.069 at Weissfluhjoch. These cases could reflect atmosphere/surface assumptions, cloud enhancement, site representation or measurement effects. They prevent treating modeled clear-sky radiation as verified truth.

Splitting by observation age does not establish a simple data-quality explanation. Among available observations at least five calendar days old, mean residuals remain +0.251 UVI at Davos and +0.965 at Weissfluhjoch. Age is not a substitute for actual QC status, and these groups have different weather and missingness.

## Observation provenance and strengthened safeguards
The [PMOD/WRC site documentation](https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/) confirms the 1,610 m Davos roof installation and 2,540 m Weissfluhjoch SLF UV site. The nearby SwissMetNet stations are at 1,594 m and 2,691 m. Approximate separations are 1.77 km and 1.10 km; the coarse published UV coordinates are not improved by guessing. Both PMOD sites have colocated SW instrumentation, but a current machine-readable delivery of that colocated record was not obtained. The SwissMetNet replacement therefore remains a nearby-station diagnostic.

The [network's peer-reviewed methodology](https://acp.copernicus.org/articles/8/7483/2008/) documents historical calibration and 10/30-minute measurement practices. It does not certify the 2026 API values, their exact timestamps, or the current calibration of each instrument. All four original Swiss/partner UV series match the newer API retrieval at their common timestamps; lack of a revision is not proof of QC completion.

The extension freezes **179 input hashes before evaluation** and verifies them on every replay. It rejects duplicate timestamps and conflicting source revisions, preserves missing pairs, records named site identities and model distances, and stores production/analysis code hashes and package versions. Expected hashes are never regenerated from inputs during a validation check. Float32 forecast values are promoted before CSV export so independently recomputed scores retain their original precision.

**Source: MeteoSwiss** for ground radiation, sunshine, pressure, metadata and ICON. [Timestamp documentation](https://opendatadocs.meteoswiss.ch/general/download); [quality-control FAQ](https://opendatadocs.meteoswiss.ch/general/faq); [public UV API](https://uv-data.i-med.ac.at/public/data/?product=uve&start=2026-08-29&stop=2026-09-06); [CAMS dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts).

## Validation boundary and next work
The original mountain discrepancy is reinforced, but **operational readiness is not established**. The main residual barriers are independent calibrated UV metadata, colocated radiation, missing observations, a single forecast weather day, and incomplete regime/season coverage. The 4 September forecast query returned no data under the public 24-hour retention policy. It was not replaced with a later initialization or reanalysis and labeled a forecast.

The historical experiment is broader in time but conditional on observed SW and pressure; it cannot measure end-to-end forecast skill. Neither temporal screening, within-hour cloud maxima, snow-albedo treatment, long-term calibration stability nor a full seasonal hindcast is observationally validated. No iid confidence intervals or significance claims are made from correlated station-hours.

Next, obtain documented colocated UV/SW records and calibration/QC/averaging metadata; assemble an archive of distinct forecast weather days and issue-time inputs; predefine seasonal/regime benchmarks and hold out evaluation cases. Test corrections and alternative cloud representations against both the current inversion and the gray baseline. Do not infer a universal correction from the present positive average errors.

## Questions raised by the expanded evidence
Does the gray baseline win after shortwave forcing errors are removed at truly colocated instruments? Are the large high-altitude errors associated with clouds below the station that the effective uniform-cloud approximation cannot represent? How much of the persistent Weissfluhjoch residual follows spatial separation and surface assumptions? Do sunny/low-sun/snow regimes and independent seasons reverse the ranking?
