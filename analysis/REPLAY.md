# Archive replay guide

The analysis modules use fixed study directories under `work/`. They contain
source data, hashes, scores and reports. The versioned
[campaign definitions](campaigns/README.md) provide sample and native-cell
mappings; the associated observations and forecast files are separate inputs.

## Environment

```sh
uv sync --locked --extra cams --group analysis
```

Add `--group notebooks` to execute notebooks with nbclient/ipykernel. CAMS
acquisition uses the configured ADS client. Native historical ICON and DWH
extraction require authorized MeteoSwiss archive access on Balfrin.

For native extraction, use a Slurm CPU allocation with the MeteoSwiss module
environment, explicit scratch/log paths and core dumps disabled. The tested
adapter uses the installed ecCodes module with `FINDLIBS_DISABLE_PACKAGE=1`.
`extract_multiyear` accepts `--campaign`, `--output`, `--mode icon|observations`,
`--shard`, `--shards` and `--workers`; use `--help` for its current options.

## Archive dependencies

| Directory | Inputs or dependencies |
|---|---|
| `scientific-validation-20260906` | Original SwissMetNet records and source metadata |
| `scientific-hardening-20260906` | Normalized ICON grids, CAMS, public UV and original SwissMetNet archive |
| `scientific-multiyear-20260906` | Native ICON columns, DWH windows, WOUDC UV and CAMS; uses the hardening source grid |
| `product-readiness-20260906` | Full-day native extraction, product inputs and Payerne reservation; reuses the multi-year UV archive |
| `independent-payerne-20260906` | Monthly PANGAEA instrument/source inventory |
| `swiss-uv-sites-20260906` | Swiss UV/CAMS/DWH inputs; verification also uses the product extraction and source grid |
| `product-physics-20260906` | libRadtran reference inputs and outputs |
| `product-delivery-20260906` | Recomputed outputs from the product-readiness inputs |

Restore source files with their relative paths and compare their checksums with
the frozen manifests. Expired public forecasts require the archived inputs or
access to the historical native archive. Changing a data directory alone does
not create a new campaign; dates, grid mapping and source definitions must also
be specified.

## Multi-site hourly study

```sh
uv run --no-sync python -m analysis.fetch_scientific public
uv run --no-sync python -m analysis.fetch_scientific cams
uv run --no-sync python -m analysis.fetch_scientific freeze
uv run --no-sync python -m analysis.scientific
uv run --no-sync python -m analysis.verify_scientific
uv run --no-sync python -m analysis.report_scientific
```

The public stages supplement the required saved ICON grids. `freeze` creates
expected hashes once, then checks those hashes on subsequent calls. Results
include matched rows, exclusions, figures, a report and a companion notebook.

## Multi-year shortwave and UV

After native extraction and DWH retrieval, `analysis.multiyear.freeze_inputs()`
records the native input identities. Acquire and freeze the UV sources with:

```sh
uv run --no-sync python -m analysis.fetch_multiyear_uv observations
uv run --no-sync python -m analysis.fetch_multiyear_uv cams --year 2024
uv run --no-sync python -m analysis.fetch_multiyear_uv cams --year 2025
uv run --no-sync python -m analysis.fetch_multiyear_uv freeze
uv run --no-sync python -m analysis.multiyear
uv run --no-sync python -m analysis.verify_multiyear
uv run --no-sync python -m analysis.multiyear_uv
uv run --no-sync python -m analysis.verify_multiyear_uv
uv run --no-sync python -m analysis.report_multiyear
```

The integrator supports nominal 10-second and 60-second WOUDC samples, with
maximum gaps of 30 and 75 seconds respectively. Hourly bounds are exact and
missing observations remain in the exclusion ledger.

## Daily products and physical sensitivity

With the required native, CAMS and observation archives present:

```sh
uv run --no-sync python -m analysis.product_analysis
uv run --no-sync python -m analysis.verify_product_analysis
uv run --no-sync python -m analysis.report_product
uv run --no-sync python -m analysis.replay_product
```

`replay_product` checks source hashes, computes native UV, round-trips NetCDF,
exports daily JSON and compares physical arrays and product fields. File hashes
can differ when runtime metadata changes. `analysis.product_physics` additionally
requires the libRadtran installation referenced by its configuration.

The Swiss-site workflow is listed in the [analysis guide](README.md#swiss-measurement-comparison).
Generated reports and executed notebooks remain local. The report generators
leave reviewed Markdown findings unchanged.
