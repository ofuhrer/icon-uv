# Development and artifact policy

Keep the repository small enough to understand and sufficient to rebuild the
tool and reproduce its scientific methods. Grid-to-station mismatch in complex
terrain is expected; improvements should serve useful UV values and categories,
not pursue exact agreement at every instrument.

## Versioned content

| Content | Decision |
|---|---|
| `icon_uv/`, regression tests, `pyproject.toml`, `uv.lock` | Retain implementation, contracts and the resolved development environment. |
| `icon_uv/data/rt.npz` | Retain this 202 kB runtime dependency so users need no solver installation. Changes require a new qualification record. |
| `icon_uv/data/daily-uv-v1.schema.json` | Retain the public data contract with the implementation and schema tests. |
| `examples/`, `analysis/product_locations.example.json` | Retain explicit example geometry/configuration; these are not operational station catalogs. |
| `analysis/*.py` | Retain acquisition, scoring, independent verification and report generators. Earlier scripts are dependencies of later studies, not disposable duplicates. |
| Protocols, campaign definitions, concise findings | Retain the declared samples, assumptions, acceptance criteria and scientific history. Older milestones are labelled in the analysis index. |

The `analysis/*GOAL.md` files record product requirements and evaluation scope;
they are retained scientific design documents. They are not active task state.

## Local, untracked content

Use `work/<study>/` for downloaded ICON/CAMS/UV/DWH data, source metadata and
calibration inventories, frozen input hashes, extraction/Slurm scripts and logs,
raw score tables, generated JSON/NetCDF, plots, HTML/PDF reports, executed
notebooks, solver installations and reference caches. Credentials stay in the
normal external client configuration. Do not copy them into `work/` or Git.

Generated files are not included in the wheel or source distribution. The
source distribution includes the analysis source, tests and small experiment
definitions; the wheel contains only the runtime package, table and schema.
Reviewed findings are edited deliberately. Report generators write into local
result directories and do not overwrite versioned findings.

Local does not mean disposable. Preserve frozen observations, expiring forecast
inputs, their identities and any solver/data installation needed for replay.
Back up those directories separately when transferring or removing a checkout;
a Git clone alone does not restore them. Do not rewrite frozen expected hashes
to accommodate changed inputs or code. Start a new study or restore the exact
source snapshot recorded for the old one.

Rebuildable Python/test caches and packaging build directories may be discarded.
One-off access probes, rejected tables and intermediate runs stay local unless
their method is needed to explain or reproduce a retained result.

## Working environment and checks

```sh
uv sync --locked --extra cams --group analysis
uv run --no-sync pytest -q
uv run --no-sync icon-uv --help
uv build --out-dir work/build-check
git diff --check
```

Add `--group notebooks` when executing generated notebooks. Analysis packages
are development groups, not forecast runtime dependencies. Run analysis modules
from the repository root with `uv run --no-sync python -m analysis.<module>`.
See [the replay guide](analysis/README.md) for required local inputs and access.
Tests use synthetic fixtures and temporary directories; ordinary tests require
neither DWH/ADS credentials nor the local measurement archive.

Build candidate radiation tables under `work/`; compare their numerical and
product effects before deliberately replacing the shipped table. Preserve the
source/provider attribution with any derived data that is later distributed.

## Cleanup record — 6 September 2026

Seven top-level generated JSON/notebook files were moved to
`work/initial-validation-20260905/` and removed from the versioned file set. Their
original contents, the previous long validation record and every pre-cleanup
source file are preserved under `work/repository-cleanup-20260906/source-before/`.
No frozen study inputs, observation records or RT caches were removed. Four
small campaign/reservation definitions were copied unchanged into
`analysis/campaigns/`, with checksums. Historical figure/report links refer to
explicitly local artifacts, not files promised by a fresh checkout.
