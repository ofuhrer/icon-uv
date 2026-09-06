# Development

## Set up and test

```sh
uv sync --locked --extra cams --group analysis
uv run --no-sync pytest -q
uv run --no-sync icon-uv --help
uv build --out-dir work/dist
```

The normal tests use synthetic fixtures and temporary files; they require no
DWH/ADS credentials or downloaded measurement archive. Add `--group notebooks`
when executing analysis notebooks. `uv.lock` records resolved dependencies;
analysis and notebook packages are separate from the forecast runtime.

## Project layout

| Path | Purpose |
|---|---|
| `icon_uv/data.py` | ICON/CAMS acquisition, normalization and NetCDF output |
| `icon_uv/radiation.py` | Radiation-table interpolation, cloud inversion and solar geometry |
| `icon_uv/products.py` | Hourly grid, point and observation-comparison APIs |
| `icon_uv/daily.py` | Daily peaks, location support and JSON export |
| `icon_uv/cli.py` | Command-line interface |
| `icon_uv/build_table.py`, `icon_uv/validate.py` | Table generation and numerical reference checks |
| `icon_uv/data/` | Bundled lookup table and daily JSON Schema |
| `docs/` | Usage, field reference and method documentation |
| `analysis/` | Research acquisition, scoring, verification and reporting tools |
| `tests/` | Input, numerical, calendar, output and regression checks |

## Data and generated files

Keep source, tests, examples, schemas, campaign definitions and reviewed findings
in Git. The small radiation table is also versioned because it is needed at
runtime. Downloaded forecasts, observations, detailed source metadata, generated
score tables, plots, reports, notebooks and logs belong under `work/<study>/`.
That directory is ignored by Git and excluded from distributions.

Preserve the local inputs and hashes needed to reproduce a study, especially
forecasts that expire from the public archive. A clone supplies code and sample
definitions; its data archives must be restored or retrieved separately. New
inputs or methods should produce a new run identity rather than overwrite an
existing frozen identity. Credentials use the normal external client setup.

The wheel contains the runtime package, table, schema and license. The source
distribution additionally contains documentation, tests and analysis methods.
Report generators write local results; reviewed findings are edited separately.

## Change the radiation table

Generate a candidate under `work/` with an external libRadtran installation:

```sh
uv run --no-sync icon-uv build-table --lib /path/to/libRadtran-2.0.6 \
  --cache work/rt-cache --output work/candidate_rt.npz
uv run --no-sync python -m icon_uv.validate --table work/candidate_rt.npz \
  --lib /path/to/libRadtran-2.0.6 --cache work/rt-cache \
  --output work/candidate_rt_validation.json
```

The reference cache identifies the solver executable, its data, reference code
and numerical settings by content hashes. See [the table record](analysis/TABLE_PROVENANCE.md).
When updating the bundled table, retain the new reference results and update
that record. Recompute saved grids before using them with a different table;
point and daily APIs check the table identity.

For scientific comparisons and archived runs, see [analysis tools](analysis/README.md).
For output-format changes, update the schema, field documentation and relevant
tests together. Run `git diff --check` and inspect package contents before release.

## License

The project uses the [BSD 3-Clause License](LICENSE). Preserve attribution for
any third-party code or data introduced by a contribution.
