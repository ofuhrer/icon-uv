# Daily-peak comparison at Davos

This comparison uses the fixed Davos instrument and prescribed UV albedo 0.05.
For additional sites and periods, see the [Swiss-site results](SWISS_UV_FINDINGS.md).

## Product-level evidence

| Day | Method | Dates | MAE (UVI) | Within 1 displayed unit | Same category |
|---|---|---:|---:|---:|---:|
| 0 | Native SW | 66 | 0.642 | 84.8% | 71.2% |
| 0 | Gray baseline | 66 | 0.707 | 81.8% | 68.2% |
| 0 | Measured-SW attribution | 66 | 0.367 | 97.0% | 81.8% |
| 1 | Native SW | 65 | 0.562 | 92.3% | 78.5% |
| 1 | Gray baseline | 65 | 0.651 | 90.8% | 80.0% |
| 1 | Measured-SW attribution | 65 | 0.329 | 98.5% | 90.8% |

Day 0/1 are separate valid dates, not paired lead-time degradation estimates.
All entries above use one fixed Davos UV instrument, full-day observation
coverage, prescribed UV albedo 0.05 and reconstructed 30-minute peaks.

[Local figure: Product scorecard](../work/product-readiness-20260906/results/product_scores.png)

The native method has a modest paired daily-MAE advantage over the gray baseline
on these data. This is a different metric from the earlier hourly comparison.
Substituting nearby measured SW reduces native MAE by 0.275
UVI (paired seasonal block-bootstrap 95% interval
0.126–0.431). This identifies shortwave input
error as a useful development priority, but the substitution is not a forecast
and the two observing locations are not identical.

Day 0: within-one 95% interval 75.8%–92.4%; category agreement 62.1%–80.3%. Day 1: within-one 95% interval 86.2%–96.9%; category agreement 67.7%–87.7%. The 90% within-one and 80% category targets are therefore not
established by their lower uncertainty bounds. Summer initialization-day category
agreement is only 60% on 20 dates; pooled winter accuracy is not sufficient.

No two-category underestimates occur among the 66 primary dates; one occurs
among 65 following-day dates. A zero-event empirical bootstrap gives [0,0],
which cannot bound the probability of an unseen event and is not a reliability
guarantee. There are no observed extreme-category days and only 12/14 very-high
days. Primary native forecasts miss the observed >=8 category on 6/12 dates.
The sample has limited rare-category and geographical coverage.

## Temporal resolution matters at display precision

Day 0: 20/66 displayed integers change; median peak difference 0.117, 90th percentile 1.043 UVI. Day 1: 19/65 displayed integers change; median peak difference 0.123, 90th percentile 1.197 UVI. These differences compare raw observed 30-minute and
clock-hour maxima; the reconstructed model cannot resolve actual subhourly cloud
evolution. The contract keeps that limitation explicit. Daily aggregation must
not silently use a partial 08–16 UTC sample.

## Complete-input product demonstration

The retained recent example uses 1781 native cells, actual ICON SNOWC and 12
solar samples per hour. It produces 54 entries: 12 towns/vicinities and five
illustrative mountain regions at 1000/2000/3000 m, for two days. All entries have
complete required daylight/support in this example. Regions use native terrain
cells near each altitude, not a vertically shifted valley cloud column.

The grid calculation took about 13.5 s on this Mac, excluding data retrieval,
export and startup; this is a measured example, not an operational latency SLA.
The example's issuance is fixed for replay and does not prove historical input
delivery time. Catalog coordinates/boxes are explicitly illustrative. Structural
`ok` status means input-contract checks passed, not validated forecast skill.

[Interface and replay instructions](PRODUCT_DATA_INTERFACE.md)
and [example JSON](../work/product-readiness-20260906/product-example.json).

## Verification

All 150 new native cases and 300 DWH windows are retained separately from the
prior campaign. All eight Slurm tasks completed successfully. The independent
bridge reconciled 1,836,000 original
native boundary values exactly. Independently interpolating raw UV measurements
to a one-second grid and integrating checked 131
daily maxima, maximum difference 3.4e-13
UVI. Independent scalar arithmetic checked 600
summary values. Repository tests: 98 passed, with the pre-existing netCDF4 import
warning. Frozen inputs, source identities and all date-level exclusions are saved.
