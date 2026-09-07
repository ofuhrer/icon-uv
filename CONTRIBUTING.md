# Development

## Set up and test

```sh
uv sync --locked --extra cams
uv run --no-sync pytest -q
uv run --no-sync icon-uv --help
uv run --no-sync python tools/generate_schemas.py --check
uv build --out-dir work/dist
uv run --no-sync python tools/check_distribution.py work/dist
```

The normal tests use synthetic fixtures and temporary files; they require no
DWH/ADS credentials or downloaded measurement archive. `uv.lock` records resolved
dependencies, including the development tools used for these checks.
GitHub Actions runs these checks on Python 3.11 and 3.13. The suite includes a
credential-free saved-input example using the real bundled radiation table.
The distribution check installs the wheel in an isolated environment outside
the source tree and loads every packaged schema and the table.

## Project layout

| Path | Purpose |
|---|---|
| `icon_uv/data.py` | ICON/CAMS acquisition, normalization and NetCDF output |
| `icon_uv/radiation.py` | Radiation-table interpolation, cloud inversion and solar geometry |
| `icon_uv/products.py` | Hourly grid, point and observation-comparison APIs |
| `icon_uv/daily.py` | Daily peaks, location support and JSON export |
| `icon_uv/ensemble.py` | Member identity, coverage and ensemble reductions |
| `icon_uv/locations.py` | Shared location definitions and native/adjusted support selection |
| `icon_uv/state.py`, `icon_uv/evaluation.py` | Saved-state validation and shared sampled UV evaluation |
| `icon_uv/schema.py`, `tools/generate_schemas.py` | Consumer schema selection and contract generation |
| `icon_uv/cli.py` | Command-line interface |
| `icon_uv/build_table.py`, `icon_uv/validate.py` | Table generation and numerical reference checks |
| `icon_uv/data/` | Bundled lookup table and daily JSON Schema |
| `docs/` | Usage, field reference and method documentation |
| `examples/` | Point geometry, daily-product catalog and UV map example |
| `tests/` | Input, numerical, calendar, output and regression checks |

## Data and generated files

Keep source, tests, examples, schemas, user documentation and the bundled
radiation table in Git. Research tools, campaign definitions, downloaded data,
notebooks and generated results stay local. The curated map snapshot in
`examples/map/index*.json` and `examples/map/index.html` is an exception: keep it
checked in so the example works immediately. Edit `examples/map/template.html`
and regenerate `index.html` when changing its presentation. Use `work/<study>/` for new study
inputs and outputs; it is ignored by Git and excluded from distributions.

Preserve local inputs, environment locks and source hashes when retaining a
study, especially forecasts that expire from the public archive. Summarize
relevant methods, results and sample coverage in [validation](docs/validation.md).
Credentials use the normal external client setup.

The wheel contains the runtime package, table, schema and license. The source
distribution additionally contains documentation, tests and examples.

## Change the radiation table

Generate a candidate under `work/` with an external libRadtran installation:

```sh
uv run --no-sync icon-uv build-table --lib /path/to/libRadtran-2.0.6 \
  --cache work/rt-cache --output work/candidate_rt.npz
uv run --no-sync python -m icon_uv.validate --table work/candidate_rt.npz \
  --lib /path/to/libRadtran-2.0.6 --cache work/rt-cache \
  --output work/candidate_rt_validation.json
```

The bundled `icon_uv/data/rt.npz` contains 10,368 reference columns and embeds
its physical configuration, described in the [calculation method](docs/method.md).
Its SHA-256 is
`a33db2d4b2806f216eef356c761460383bb4a9fca53e3b958715bc12e6d6dcba`.

The reference cache identifies the solver executable, its data, reference code
and numerical settings by content hashes. When updating the bundled table,
retain the candidate configuration and reference results locally, update this
identity and summarize the checks in the validation documentation. Recompute
saved grids before using them with a different table; point and daily APIs
check the table identity.

For output-format changes, update the schema, field documentation and relevant
tests together. Run `git diff --check` and inspect package contents before release.

The v1 JSON schema is the shared base for `tools/generate_schemas.py`. That script
applies the v2 date, v3 ensemble and v4 location/geometry additions and writes the
standalone published schemas. Run it after deliberate schema edits, then use
`--check` to ensure artifacts are current. Published v1–v3 contracts and hashes
remain stable; evolve shared-location products in a new version when compatibility
requires it. Runtime callers use `load_schema(payload)` to select the artifact.

## License

The project uses the [BSD 3-Clause License](LICENSE). Preserve attribution for
any third-party code or data introduced by a contribution.
