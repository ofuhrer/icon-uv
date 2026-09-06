# Earlier study replay recipes

This guide records the earlier study milestones and their exact local archive
layout. Counts and unscored-site statements describe those checkpoints. For the
current Swiss assessment and locked environment, start with [the index](README.md).
Report generation now writes local outputs only; reviewed findings are maintained
separately.

Read [the protocol](SCIENTIFIC_PLAN.md) and [the findings](FINDINGS.md). These
scripts are repository analysis tools, not additions to the distributed
forecast runtime. They make no empirical fit or production algorithm change.

The extension has two deliberately separate evaluations:

- Three ICON initializations for 5 September 2026, at 20 geographically covered
  UV sites (14 have complete primary-window measurements) and 135 SW stations.
- An observation-driven conversion experiment at Davos/Weissfluhjoch over
  29 August–5 September. This is not a multi-day ICON hindcast.

## Environment

From the repository root, create an optional local analysis environment:

```sh
uv venv work/scientific-env
uv pip install --python work/scientific-env/bin/python -e '.[cams]' \
  matplotlib nbformat nbclient ipykernel
```

The executed artifact in this session used
`work/scientific-validation-20260906/env/bin/python`. Exact calculation versions
and source hashes are in `work/scientific-hardening-20260906/results/run_identity.json`.
No new project runtime dependency is required.

## Inputs and provenance

The archived local directory `work/scientific-hardening-20260906` contains three
normalized ICON files, eight CAMS cycles (and the original combined GRIB), the
public UV record/site metadata, and two recent SwissMetNet records. The frozen
manifest also references the previously archived regional station files under
`work/scientific-validation-20260906`. Preserve both directories for replay.

Acquisition code is explicit and bounded to this protocol:

```sh
work/scientific-env/bin/python -m analysis.fetch_scientific public
work/scientific-env/bin/python -m analysis.fetch_scientific cams
work/scientific-env/bin/python -m analysis.fetch_scientific freeze
```

The public stage reuses existing files. It cannot recover expired ICON assets;
their public retention is only 24 hours. CAMS requires the user's configured ADS
client and accepted dataset terms. Credentials are not copied into artifacts.
Original raw ICON asset checksums remain in the normalized files' `icon_sources`
attributes. Public observation retrieval URLs/timestamps/checksums are recorded
in `downloads.json`, with earlier sources in the previous analysis manifest.

`freeze` creates the expected input hashes once. Subsequent calls verify the
existing manifest and refuse changed inputs. It is not a refresh operation.
To extend to another period, choose a new data directory and explicit protocol;
do not edit a frozen expected hash just to make a replay pass. The input checks
detect changes relative to the saved manifest; they are not a cryptographic
signature or independent certification of a source's accuracy.

## Replay and verify

```sh
work/scientific-env/bin/python -m analysis.scientific
work/scientific-env/bin/python -m analysis.verify_scientific
work/scientific-env/bin/python -m analysis.report_scientific
uv run pytest -q
```

`scientific.py` verifies frozen inputs before calculations. It retains every
requested UV interval and its exclusion reason; uses a fixed daylight window;
matches site-hour pairs across cycles; separates unknown sunshine; and computes
daily, pooled, regime, age and surface-sensitivity results. Independent checks
reconcile raw timestamps, unit conversions, metrics and paired differences.

The core scoring function rejects nonfinite pairs rather than silently deleting
them. The summarizer records exclusions before scoring. A UVI-specific radiant
exposure conversion is separate from the generic UV/SW error metrics.

`report_scientific.py` exports three Matplotlib figures as PNG/PDF, a canonical
`artifact.json`, a Markdown report, and a companion notebook. It retains an
existing notebook rather than overwriting executed outputs. Its conclusions
refer to this frozen protocol; a different period requires rewritten findings.

Execute the companion notebook with the analysis interpreter:

```python
from pathlib import Path
import nbformat
from nbclient import NotebookClient

root = Path.cwd()
path = root / 'work/scientific-hardening-20260906/results/expanded_scientific_validation.ipynb'
notebook = nbformat.read(path, as_version=4)
NotebookClient(notebook, timeout=240, kernel_name='python3',
               resources={'metadata': {'path': str(root)}}).execute()
nbformat.write(notebook, path)
```

An installed Data Analytics report plugin can package `artifact.json` with its
bundled `deliver_portable_artifact.mjs --input <artifact.json> --output <report.html>`
using the plugin's Node runtime. This is optional presentation tooling; the
calculations, notebook, Markdown and standalone figures do not depend on it.

## Scientific boundary

The historical surface-albedo scenarios and gray-cloud comparator are unfitted
diagnostics. Missingness, unconfirmed current UV averaging/QC/calibration,
non-colocation and issue-time availability prevent an operational qualification.
An older observation is not automatically QC-qualified. Day omission ranges
are sensitivity results, not independent-sample confidence intervals. Full
seasonal, snow and terrain validation still requires suitable observations and
an archive of independent forecast cases.

At the original hardening checkpoint, the repository test run passed 70 tests with one NumPy/netCDF4 import
warning (`numpy.ndarray size changed`). A focused diagnostic treating runtime
warnings as errors stops at that dependency import. The warning is recorded,
not filtered away or interpreted as proof of corrupted values; raw-source and
round-trip checks pass. Resolving that binary-build warning remains a separate
environment qualification item.

## Multi-year expansion

The [new protocol](MULTIYEAR_PLAN.md), [fixed 150-date roster](multiyear_cases.csv),
[UV protocol](MULTIYEAR_UV_PLAN.md) and [multi-year findings](MULTIYEAR_FINDINGS.md)
extend the study across August 2024–August 2026. Native SW cases and WOUDC UV
POI diagnostic cases are counted separately. This extension makes no production
algorithm change or empirical fit.

Preserve `work/scientific-multiyear-20260906`: `campaign.json` contains the full
native-cell/station mapping, exact dates, source-grid checksum and archive root;
`icon/` holds selected native boundary arrays plus per-message GRIB identities
and hashes; `observations/` holds the original DWH CSVs and quality categories;
`uv/` holds public WOUDC files, CAMS GRIBs and source manifests. Frozen hashes
must not be rewritten to accommodate changed inputs. Start a new directory and
protocol for another campaign.

`extract_multiyear.py` runs on CSCS CPU nodes under the Balfrin environment
instructions. It accepts `--campaign`, `--output`, `--mode icon|observations`,
`--shard`, `--shards` and `--workers`. The executed Slurm script and acquisition
logs are retained in the work directory. Extraction used eight single-CPU
shards, with explicit scratch/log paths and core dumps disabled. Use the
installed ecCodes module and `FINDLIBS_DISABLE_PACKAGE=1` with this environment;
the pip-provided binary-library loading stalled on the compute node. The newer
Python binding recommends a newer ecCodes C library; the recommendation is
retained in the logs, and extracted numbers passed the independent bridge test.

Old GRIBs express lead time in minutes. The adapter normalizes the time accessor
to hours while retaining original message hashes and raw time-unit metadata;
fractional/mismatched leads are rejected. Surface direct plus diffuse radiation
is de-averaged into hourly SW. Missing archived snow depth is retained as NaN;
it is not required for SW scoring, and it is never converted to snow fraction.

Public UV and CAMS acquisition (CAMS uses the already configured ADS account):

```sh
work/scientific-env/bin/python -m analysis.fetch_multiyear_uv observations
work/scientific-env/bin/python -m analysis.fetch_multiyear_uv cams --year 2024
work/scientific-env/bin/python -m analysis.fetch_multiyear_uv cams --year 2025
work/scientific-env/bin/python -m analysis.fetch_multiyear_uv freeze
```

After all 150 native extractions and 300 DWH windows are available, freeze them
once with `analysis.multiyear.freeze_inputs()`. Replay and verify locally:

```sh
work/scientific-env/bin/python -m analysis.multiyear
work/scientific-env/bin/python -m analysis.verify_multiyear
work/scientific-env/bin/python -m analysis.multiyear_uv
work/scientific-env/bin/python -m analysis.verify_multiyear_uv
work/scientific-env/bin/python -m analysis.report_multiyear
uv run pytest -q
```

The analysis environment additionally requires pandas, Matplotlib, nbformat,
nbclient and ipykernel. The result directory contains all station-hour rows,
coverage/exclusion ledgers, seasonal/regime/daily summaries, standalone PNG/PDF
figures, a Markdown report and `multiyear_validation.ipynb`. Execute this notebook
with the analysis interpreter/nbclient as in the earlier example, using its new
path. It verifies frozen inputs and recomputes summary checks from the retained
pairs. Rebuilding the report regenerates the notebook; execute it again afterward.

The fixed WOUDC instrument has both ~10 s and ~60 s sampling periods. The hourly
integrator uses exact bounds and permits gaps up to 30 s and 75 s respectively;
a missing minute is rejected. Cadence, per-file processing metadata and missing
observations are retained. These records do not supply per-sample QC flags.

## Daily product readiness

The [completed readiness assessment](PRODUCT_READINESS_ASSESSMENT.md) applies
the user's map-product objective: useful displayed values, categories and
dependable input/output behavior. It brings together the fixed product contract,
full-day 150-case native campaign, 66/65 observed Davos daily peaks, independent
Payerne metadata assessment, 72 additional RT stress calculations and a complete
54-entry town/mountain two-day replay. The current suite has 106 passing tests
with the previously recorded netCDF4 import warning.

The data interface is suitable for an internal integration pilot. Public
scientific qualification remains unsupported by the present coverage and scores.
Payerne's 84 reserved dates have not been scored or used for fitting. See
[the source assessment](PAYERNE_SOURCE_ASSESSMENT.md),
[physical protocol](PRODUCT_PHYSICS_PLAN.md) and
[export/schema/replay documentation](PRODUCT_DATA_INTERFACE.md).

Additional retained directories are `work/independent-payerne-20260906`
(metadata/source inventory), `work/product-physics-20260906` (frozen direct RT
inputs and results) and `work/product-delivery-20260906` (complete local replay,
schema validation, tests, resource logs and final assessment identity).
