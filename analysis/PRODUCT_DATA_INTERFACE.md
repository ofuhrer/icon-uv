# Daily UV data interface, v1

The `icon-uv daily` command generates machine-readable data for a map renderer.
It does not publish a forecast. [Contract v1](PRODUCT_CONTRACT_V1.md) defines the
quantity, time/calendar, rounding, categories, spatial support and failure rules.
The initial catalog is illustrative: towns use named SwissMetNet station
vicinities, and regions use explicitly approximate bounding boxes.

## Replay the recent complete-input example

The retained example uses the 6 September 2026 00 UTC ICON control cycle and
5 September 12 UTC CAMS cycle. Production SNOWC is present. Its payload is a
replay with issuance fixed at 06 UTC; it does not assert that these downloaded
files were delivered at that historical time.

```sh
uv run icon-uv daily \
  --grid work/product-readiness-20260906/uv_product_support_20260906.nc \
  --catalog analysis/product_locations.example.json \
  --issued-at 2026-09-06T06:00:00Z \
  --output work/product-readiness-20260906/product-example.json
```

The source grid was generated with `compute_grid(..., samples=12)` from saved
complete-day ICON/CAMS inputs, selecting the union of catalog support cells.
The example contains 12 town/vicinity entries and 15 region/elevation entries
for each day. Regional support retains native pressure, cloud and snow state.
Neither town coordinates nor regional aggregation reproduce an official catalog.

## Consumer rules

Top-level fields include `schema_version`, `contract_sha256`, `issued_at`,
`timezone`, `peak_definition`, `category_basis`, `catalog_sha256`, source-file and
radiation-table hashes, `sources`, scientific `qualification`, assumptions and
`entries`. The source reference times and ages are relative to the supplied
issuance, allowing deterministic replay. `input_sha256` identifies the exact
saved grid used by the CLI.

Each entry identifies its location and altitude, `valid_date`, lead `day`, input
quality `status`, `reasons`, selected/valid native-cell counts and:

- `uvi`: unrounded aggregate; `display_uvi`: half-up integer; `category`: low,
  moderate, high, very_high or extreme. Values above 11 remain numerical values;
  a renderer may label the extreme class 11+ without truncating the data.
- Valid entries include the aggregation method, contributing native cell IDs,
  their minimum/maximum/median daily UVI, combined model quality bitmask and
  range of peak-window start times. A regional aggregate has no single physical
  peak instant, because its constituent cells can peak at different times.
- Towns additionally provide the selected source point, altitude difference,
  and the UTC start of their 30-minute peak window.

`ok` means the documented input/support rules pass. It is **not** a scientific
qualification label. `degraded` means an explicitly accepted partial regional
support (at least 95% valid). `unavailable` has null UVI/number/category and
machine-readable reasons. Never turn null into zero or show the previous file as
a fresh forecast. No fallback is enabled in v1. Global corrupt inputs raise an
error and leave the last file unchanged; the consumer must still check issuance
and freshness. JSON writes are atomic and reject NaN/Infinity.

The reconstructed peak resolves solar evolution, not actual subhourly cloud
fluctuations. Snow albedo and the fixed atmospheric profile remain experimental.
The historic prescribed-albedo comparison and this complete-input demonstration
must retain separate validation scopes.

## Machine-readable schema and full replay

The packaged `icon_uv/data/daily-uv-v1.schema.json` uses JSON Schema 2020-12.
It checks required metadata, types, categories, null/unavailable states, support
identifiers and required provenance fields. Consumers must also check semantic
relationships: local valid dates/day pairing, raw-to-integer rounding, support
counts and freshness relative to the current clock. A schema cannot infer those
relationships from types alone. Unknown extra fields are permitted for additive
compatibility; the contract version remains explicit.

`uv run --extra cams python -m analysis.replay_product` verifies frozen source
hashes, selects native cells, recomputes UV with 12 solar samples per hour, writes
and rereads NetCDF, exports JSON and checks the schema and original example.
Outputs go to `work/product-delivery-20260906`, leaving the frozen example intact.
The new NetCDF file hash can differ because its metadata record compute runtime;
all tested physical arrays and all product fields other than that hash must
match exactly. The schema is included in the built wheel and needs no extra
runtime dependency; its verification uses the development `jsonschema` package.

## Proposed operational budget

Use the 00 UTC ICON cycle for an initial 06 UTC daily issuance, following the
demonstrated replay. This is a proposed service schedule, not a measured source
availability guarantee. Budget 15 minutes for bounded acquisition/retries after
both required input cycles become available, five minutes for native computation
and export, and five minutes for validation and transfer: **25 minutes after
input readiness**, subject to the 06 UTC deadline. Start with 1 GiB processing
memory for this small catalog and measure the actual deployment host.

If input readiness misses the deadline, show an unavailable update; do not
relabel an old file with a fresh issuance. A publication adapter must check the
expected issue cycle, valid date, source ages and successful validation before
promoting a file, and expose late/unavailable status separately from old stored
files. The existing no-fallback rule remains. Neither a scheduler nor a live
availability claim is supplied by this offline tool. Continuous availability,
network retries and source-arrival distributions need an observed shadow run
before adopting this proposed budget as an operational commitment.

## Reproduce the new historical analysis

Preserve `work/product-readiness-20260906` and the two prior scientific work
directories. The native extraction script is the existing checked adapter,
using this campaign's new boundary roster; the submitted Slurm script is saved
in the new work directory. CAMS and DWH acquisition are in `product_inputs.py`.
They require the already configured ADS account and authorized CSCS/DWH access.
Do not place credentials in the work directory.

```sh
work/scientific-validation-20260906/env/bin/python -m analysis.product_analysis
uv run pytest -q
```

The analysis first freezes inputs and verifies the prior WOUDC manifest, then
creates full-day pairs, exclusions, product scores, seasonal date-block
uncertainty and paired method comparisons under the fixed analysis plan.
Do not rewrite a frozen manifest to accept changed source files.
