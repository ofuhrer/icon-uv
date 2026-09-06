# Physical sensitivity and delivery measurements

This record describes direct radiative-transfer sensitivity calculations and
a complete local-input replay of the daily product. For observed UV errors,
see [validation results](../VALIDATION.md).

## Additional physical checks

The [physical protocol](PRODUCT_PHYSICS_PLAN.md) defines **72 direct RT
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

## Delivery implementation and evidence

The [versioned interface](PRODUCT_DATA_INTERFACE.md) supplies raw UVI, display
integer, category, local validity date, peak definition, source cycles/hashes,
native support and explicit `ok`/`degraded`/`unavailable` states. It preserves
values above 11, distinguishes zero from missing, rejects stale/future or
corrupt inputs, and writes JSON atomically. Native-cell identifiers are checked for valid integer IDs.

The full local-input replay produces **54 entries**: 12 town/vicinity values and
five regions at three elevations for each of two days, using 1,781 native cells.
All seven checked persisted physical/state arrays match the frozen example
exactly. JSON fields match exactly except the new grid-file hash, which changes
with recorded compute-runtime metadata. The packaged schema accepts the payload.

Measured local processing is **16.03 seconds**, or **17.29 seconds** including
Python/command startup, with **242 MiB peak resident memory** on this Mac.
This includes input checksum verification, CAMS decoding, native UV computation,
NetCDF write/read, JSON export and verification; it excludes network acquisition.
The separate JSON-only export takes 2.82 seconds.

Reproduce with `uv run --no-sync python -m analysis.replay_product`.
`work/product-delivery-20260906` contains the new grid, JSON, verification and
resource logs. `work/product-readiness-20260906` remains the frozen historical
scorecard and original example. The catalog is illustrative, not official
MeteoSwiss town/region geography.
