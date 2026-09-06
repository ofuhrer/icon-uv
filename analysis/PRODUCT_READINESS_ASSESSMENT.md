# Readiness for daily Swiss UV map data

6 September 2026. Assessment against [the product goal](PRODUCT_READINESS_GOAL.md).

**Ready for product integration and an internal pilot; not yet qualified as an
unattended public forecast across Switzerland.** The data interface and frozen
replay work. Evidence does not yet establish the working accuracy targets across
sites, seasons, snow conditions and the current ICON configuration. This is the
completed implementation/readiness assessment, not a claim that every scientific
target has passed.

The user's example calls for reliable displayed integers and categories, rather
than very high decimal accuracy. The findings support concentrating development
on clouds, effective snow albedo, daily peaks and representative locations.
The current radiation table is retained; no empirical correction has been fit.

## Product accuracy and useful development priorities

The native campaign contains **150 ICON initializations on 150 distinct dates**,
August 2024–August 2026: 50 times the original three initializations. It samples
six dates per month and 135 shortwave stations. This is not 150 validated UV
forecasts: historical snow fraction is unavailable, and UV diagnostics use a
prescribed albedo at the fixed Davos instrument. Full-day product scoring has
66 initialization-day and 65 next-day observations, retaining missing cases.

| Product measure | Initialization day | Next day | Working target |
|---|---:|---:|---:|
| Within one displayed UV unit | 84.8% | 92.3% | ≥90% |
| Same displayed category | 71.2% | 78.5% | ≥80% |
| Underestimated by ≥2 categories | 0/66 | 1/65 | <5%, with adequate evidence |
| Raw daily-peak MAE | 0.642 UVI | 0.562 UVI | Diagnostic |

These are site-specific point estimates, not national skill estimates. The
seasonal date-block 95% interval for initialization-day within-one accuracy is
75.8–92.4%; for category agreement it is 62.1–80.3%. The zero-event bootstrap
interval for severe underestimation cannot bound unobserved future risk. There
are no observed extreme-category days, and only 12 initialization-day very-high
days; six of those were predicted below very-high. Summer category agreement
is 60% on 20 dates. Small subgroup counts remain insufficient evidence.

Replacing forecast shortwave with nearby measured shortwave reduces
initialization-day MAE from **0.642 to 0.367 UVI**. The paired reduction is
0.275 UVI, with a date-block 95% interval of 0.126–0.431. This is an attribution
experiment, not an available forecast input or proof that all remaining error
is caused by clouds. The native UV conversion has a modest advantage over gray
scaling on this daily metric; wholesale replacement by gray scaling is not
supported. [Full scorecard and uncertainty](PRODUCT_FINDINGS.md).

Temporal definition matters even at integer precision: the observed 30-minute
and clock-hour maxima produce different displayed values on 20/66 first-day
cases. The implemented product is a 30-minute maximum on five-minute window
starts, with hourly cloud state and reconstructed solar evolution. It cannot
resolve real subhourly cloud enhancement. Changing this definition would be a
new product contract and would require rescoring.

## Additional physical checks

The frozen [physical protocol](PRODUCT_PHYSICS_PLAN.md) adds **72 direct RT
calculations**, crossing two solar angles, three elevations, two albedos and
two cloud states with summer/winter profiles and water-column sensitivities.
The unchanged runtime table infers clouds from each direct calculation's SW.
These controlled states are not independent observed weather cases.

| Direct atmosphere | States | UV conversion MAE | Maximum absolute error | Within one displayed unit | Same category |
|---|---:|---:|---:|---:|---:|
| Summer, 20 mm water | 24 | 0.064 | 0.148 | 100% | 100% |
| Winter, 20 mm water | 24 | 0.187 | 0.523 | 100% | 95.8% |
| Winter, 5 mm water | 24 | 0.103 | 0.307 | 100% | 100% |

An independently constructed input deck matches the existing reference solver
exactly for the bridge state. Every calculation passes finite/nonnegative flux
and solar-energy checks. The experiment takes 8.48 seconds, with four local
workers; all input decks, spectra, broadband outputs and identities are saved.

Changing uniform surface albedo from 0.05 to 0.8 changes reference UVI by
0.48–4.98 across the summer-profile stress states. Changing pressure-equivalent
elevation from 500 to 3000 m at fixed cloud/albedo changes it by 0.06–1.17.
These are controlled contrasts, not measured correction factors. They explain
why regional effective snow and native cloud support deserve more attention
than adding seasonal profile machinery solely to gain decimal precision.
The experiment cannot validate three-dimensional clouds, shadowed terrain or
the current linear snow-fraction-to-UV-albedo assumption.

Replay: `uv run --extra cams python -m analysis.product_physics` (requires the
retained libRadtran installation). Preserve `work/product-physics-20260906` and
the packaged RT table. Candidate physics uses its own directory and protocol.

## Independent observations and authentic inputs

[Payerne source assessment](PAYERNE_SOURCE_ASSESSMENT.md) inventories 14 UV and
14 matching shortwave monthly publications. It verifies reusable native support
at the actual BSRN site, identifies an instrument change and missing instrument
metadata, and records outstanding calibration, timestamp-support and QC
questions. **The 84 reserved dates remain unscored**; inventory counts are not
validation counts. Current observation access does not establish qualified UV
coverage at multiple sites/elevations. The existing CAMS subset cannot simply
be moved from Davos to Payerne.

The recent full-input demonstration includes authentic ICON snow fraction,
complete daylight coverage and the current model. It is a successful processing
example, not a new observation-based qualification of that configuration.
Historical prescribed-surface scores remain separately labeled. No universal
altitude percentage or valley-cloud transplant has been introduced.

## Delivery implementation and evidence

The [versioned interface](PRODUCT_DATA_INTERFACE.md) supplies raw UVI, display
integer, category, local validity date, peak definition, source cycles/hashes,
native support and explicit `ok`/`degraded`/`unavailable` states. It preserves
values above 11, distinguishes zero from missing, rejects stale/future or
corrupt inputs, and writes JSON atomically. A corrupt native-cell identifier
can no longer be silently truncated into a different integer ID.

The JSON Schema is packaged in the built wheel. The suite passes **106 tests**,
including daily/calendar/DST, support coverage, failed writes, malformed JSON
records and category consistency. A stricter diagnostic treating runtime
warnings as errors still stops at the existing netCDF4 import warning
(`Expected 16 ... got 96`); it is not suppressed. The same warning is reported
in [upstream issue 1354](https://github.com/Unidata/netcdf4-python/issues/1354).
This is recorded as an environment qualification limitation; it is not evidence
that checked arrays were corrupted, nor proof that arbitrary binary builds work.

The full local-input replay produces **54 entries**: 12 town/vicinity values and
five regions at three elevations for each of two days, using 1,781 native cells.
All seven checked persisted physical/state arrays match the frozen example
exactly. JSON fields match exactly except the new grid-file hash, which changes
with recorded compute-runtime metadata. The packaged schema accepts the payload.

Measured local processing is **16.03 seconds**, or **17.29 seconds** including
Python/command startup, with **242 MiB peak resident memory** on this Mac.
This includes input checksum verification, CAMS decoding, native UV computation,
NetCDF write/read, JSON export and verification; it excludes network acquisition.
The separate JSON-only export takes 2.82 seconds. A proposed 06 UTC issuance
with a 25-minute acquisition/processing/validation budget is documented in the
interface. Source readiness and a live availability percentage remain unmeasured.

Reproduce with `uv run --extra cams python -m analysis.replay_product`.
`work/product-delivery-20260906` contains the new grid, JSON, verification and
resource logs. `work/product-readiness-20260906` remains the frozen historical
scorecard and original example. The catalog is illustrative, not official
MeteoSwiss town/region geography.

## Completion and adoption decision

All six goal stages have concrete deliverables: frozen product semantics;
baseline and error attribution; targeted physical sensitivity and a decision to
retain the simpler table; an independent-source assessment and authentic-input
replay; a tested packaged interface and latency budget; and this readiness
decision. The work can conclude with the scientific targets unqualified, as
specified by the goal. Nothing has been published or scheduled.

Proceed with internal renderer integration using the example payload and
explicit experimental status. Before public adoption, prioritize:

1. Resolve Payerne calibration, time support and QC, then evaluate the unchanged
   candidate on all 84 reserved dates. Add qualified high-elevation/snow data and
   current-configuration UV cases; preserve an untouched set for any later fit.
2. Test improvements to cloud-driven daily peaks and effective snow albedo on
   paired cases. Adopt additional complexity only when it improves displayed
   values/categories on independent cases and relevant subgroups.
3. Finalize the town/region catalog and issuance requirements, qualify the
   deployment environment and run a shadow delivery trial measuring actual
   source arrivals, missing-data behavior and deadline compliance.
