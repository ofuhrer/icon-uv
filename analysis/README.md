# Analysis tools

These repository tools retrieve forecast and measurement data, match temporal
and spatial support, calculate errors and generate local reports. For package
usage, see the [README](../README.md); for summary statistics, see
[validation results](../VALIDATION.md).

## Environment

From the repository root:

```sh
uv sync --locked --extra cams --group analysis
uv run --no-sync pytest -q
```

The analysis group declares pandas, Matplotlib and nbformat. Add
`--group notebooks` for nbclient/ipykernel when executing generated notebooks.
Use `uv run --no-sync python -m analysis.<module>` so the repository imports and
selected environment remain stable. The RT stress study additionally requires
its retained libRadtran installation; acquisition requires the relevant archive
or ADS access. Neither is required for the normal test suite.

## Inputs and scientific identities

Small, immutable [campaign definitions](campaigns/README.md) and the 84-date
Payerne reservation are versioned. Their original `work/<study>/campaign.json`
paths remain the analysis inputs. Copy them only into a new archive, or check
byte identities before restoring an existing one. Observations, native grids,
CAMS composition, calibration metadata and the detailed input manifests remain
local. A clone contains the method and sample definition, not the measured data.

Do not edit a frozen input hash to make a changed source pass. Source snapshots
and expected hashes describe the original experiment. Reproduction against a
new source version is a new run whose differences should be recorded.

## Swiss measurement comparison

With all retained study inputs available:

```sh
uv run --no-sync python -m analysis.swiss_uv_analysis --root work/swiss-uv-sites-20260906
uv run --no-sync python -m analysis.verify_swiss_uv --root work/swiss-uv-sites-20260906
uv run --no-sync python -m analysis.swiss_spatial_sensitivity --root work/swiss-uv-sites-20260906
uv run --no-sync python -m analysis.report_swiss_uv --root work/swiss-uv-sites-20260906
```

The analysis also reads the reserved Payerne roster from the product study.
Verification and spatial sensitivity reuse its independent native extraction
and the original source grid. Payerne acquisition uses the retained monthly
inventory. See the [archive replay recipes](REPLAY.md) for those dependencies and
the earlier studies; changing only `--root` does not create a new campaign.

Acquisition entry points expose `--help`: `swiss_uv_inputs` retrieves public UV,
Payerne and CAMS; `swiss_cams_batches` provides equivalent bounded monthly CAMS
requests; `swiss_dwh_inputs` uses installed `jretrievedwh` on Balfrin.
`extract_multiyear` retrieves native archive columns; `probe_swiss_uv` and
`dwh_catalog` retain the bounded availability-discovery method. The installed
DWH path and MeteoSwiss archive paths are site-specific, not portable credentials.
Run native extraction on an appropriate Slurm allocation with the MeteoSwiss
module environment, explicit scratch/log paths and the tested ecCodes setup
listed in [the replay guide](REPLAY.md).

## Study definitions and scripts

| Analysis | Definition | Main scripts |
|---|---|---|
| Swiss UV sites | [UV protocol](SWISS_UV_PROTOCOL.md), [Payerne adapter](PAYERNE_EXPLORATORY_PROTOCOL.md), [spatial matching](SWISS_SPATIAL_SENSITIVITY.md) | `swiss_uv_analysis`, `verify_swiss_uv`, `report_swiss_uv` |
| Daily products | [Version-1 study contract](PRODUCT_CONTRACT_V1.md) | `product_analysis`, `verify_product_analysis`, `report_product` |
| Native shortwave and historical Davos UV | [Shortwave protocol](MULTIYEAR_PLAN.md), [UV protocol](MULTIYEAR_UV_PLAN.md) | `multiyear`, `multiyear_uv`, `verify_multiyear`, `report_multiyear` |
| Multi-site hourly comparisons | [Protocol](SCIENTIFIC_PLAN.md) | `scientific`, `verify_scientific`, `report_scientific` |
| Physical sensitivity | [Protocol](PRODUCT_PHYSICS_PLAN.md) | `product_physics` |

Protocols retain the sample definitions used for each analysis. Source inventory,
calibration/time-support metadata, paired values, exclusion ledgers, plots and
notebooks live in the associated local `work/<study>/` directories. The
[replay guide](REPLAY.md) lists dependencies between these archives. Links to
`work/` require those local data; a fresh clone contains the methods and campaign
definitions only.

Detailed study records are available for [Swiss UV](SWISS_UV_FINDINGS.md),
[multi-year shortwave/UV](MULTIYEAR_FINDINGS.md), [daily Davos peaks](PRODUCT_FINDINGS.md)
and [multi-site hourly diagnostics](FINDINGS.md). Sample counts from overlapping
studies should not be added as independent observations.
