# Scientific analysis

Start with [current validation status](../VALIDATION.md) and
[the broader Swiss findings](SWISS_UV_FINDINGS.md). This directory retains the
methods, fixed study definitions and reviewed evidence behind the tool. Scripts
are repository tools; they are not imported into the forecast runtime wheel.

## Study index

| Study | Design and findings | Code families |
|---|---|---|
| Swiss sites, 150 ICON dates, 583 complete site-days | [Protocol](SWISS_UV_PROTOCOL.md), [Payerne adapter](PAYERNE_EXPLORATORY_PROTOCOL.md), [spatial sensitivity](SWISS_SPATIAL_SENSITIVITY.md), [findings](SWISS_UV_FINDINGS.md) | `swiss_*`, `probe_swiss_uv`, `dwh_catalog`, `verify_swiss_*`, `report_swiss_uv` |
| Daily map-data contract and delivery | [Contract](PRODUCT_CONTRACT_V1.md), [interface](PRODUCT_DATA_INTERFACE.md), [assessment](PRODUCT_READINESS_ASSESSMENT.md) | `product_*`, `replay_product`, `verify_product_analysis`, `report_product` |
| Multi-year shortwave and historical Davos UV | [SW protocol](MULTIYEAR_PLAN.md), [UV protocol](MULTIYEAR_UV_PLAN.md), [findings](MULTIYEAR_FINDINGS.md) | `extract_multiyear`, `fetch_multiyear_uv`, `multiyear*`, `verify_multiyear*`, `report_multiyear` |
| Earlier multi-site scientific hardening | [Protocol](SCIENTIFIC_PLAN.md), [findings](FINDINGS.md) | `fetch_scientific`, `scientific`, `verify_scientific`, `report_scientific` |
| Payerne source discovery before scoring | [Reservation plan](INDEPENDENT_SITE_PLAN.md), [historical metadata assessment](PAYERNE_SOURCE_ASSESSMENT.md) | `inventory_payerne` |

The earlier studies are retained for scientific traceability and because later
analyses reuse their time integration, metric and native-input adapters. Older
statements such as “Payerne remains unscored” apply to that milestone. The latest
Swiss study accepted named-instrument months under a separate frozen protocol.
No station-to-grid sensitivity result selects a better-fitting cell retrospectively.

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

## Latest Swiss replay

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
inventory. See the [older replay recipes](REPLAY.md) for those dependencies and
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

## Outputs and retained local archives

| Local directory under `work/` | Purpose |
|---|---|
| `scientific-validation-20260906` | Original observations, reference installation/environment and detailed first evaluation |
| `scientific-hardening-20260906` | Expanded case inputs, source grid and frozen study |
| `scientific-multiyear-20260906` | 150-case native/SW campaign and historical Davos UV |
| `product-readiness-20260906` | Independent full-day native extraction, reserved roster and product examples |
| `independent-payerne-20260906` | Original monthly source/instrument inventory |
| `product-physics-20260906`, `product-delivery-20260906` | Direct RT stress checks and complete delivery replay |
| `swiss-uv-sites-20260906` | Latest inputs, identities, source qualification, scores and report |
| `swiss-uv-pre2026-20260906` | Intermediate subset retained for exact replay comparison |
| `initial-validation-20260905` | Initial generated JSON reports and one-day inspection notebook |

All generated figures, notebooks and score tables stay under these local
archives. Report scripts write local outputs; updating reviewed Markdown findings
is a deliberate editing step. Links to `work/` are optional local evidence and
will not resolve in a fresh clone. See [the artifact policy](../CONTRIBUTING.md)
for retention, packaging and backup decisions.
