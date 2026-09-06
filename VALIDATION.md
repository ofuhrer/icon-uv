# Validation status

Updated 6 September 2026. The tool is suitable for continued internal development
of Swiss UV map data. Its numerical implementation, daily export contract and
measurement comparisons have been exercised independently. Public operational
qualification remains separate from this engineering assessment.

## Current observational evidence

The fixed campaign contains 150 ICON initializations on distinct dates from
August 2024 to August 2026. The latest Swiss assessment yields 583 complete
site-days at three locations, with both forecast days evaluated separately.

| Site | Complete days, forecast day 1 / 2 | Peak MAE (UVI), day 1 / 2 | Within one displayed unit |
|---|---:|---:|---:|
| Davos | 146 / 146 | 0.613 / 0.635 | 89.0% / 88.4% |
| Weissfluhjoch | 100 / 99 | 0.777 / 0.854 | 86.0% / 80.8% |
| Payerne | 46 / 46 | 0.484 / 0.502 | 97.8% / 93.5% |

These are daily maxima on common half-hour windows with prescribed UV albedo
0.05. The historical archive lacks production snow fraction. At Payerne, minute
observations also support the actual 30-minute rolling peak sampled every five
minutes: MAE is 0.523 / 0.521 UVI. The mountain feed cannot directly verify that
finer temporal support. No empirical correction was fitted to these results.

Grid-to-station differences are expected in complex terrain. The sensitivity
study quantifies their effect; exact station agreement is not a prerequisite
for useful regional products. Interpret errors together with spatial support,
season, snow conditions, displayed values and category boundaries. Measured
shortwave substitutions improve all three sites, identifying a practical
cloud/shortwave development priority.

Jungfraujoch and Locarno-Monti were located through DWH, but corrected UV was
unavailable. Payerne spring instrument metadata and much of the 2026 Weissfluhjoch
record are missing. These gaps limit regional and seasonal conclusions. Extreme
UV and regional elevation-band accuracy are not established by the sample.
See [the Swiss findings](analysis/SWISS_UV_FINDINGS.md) for category errors,
dependence-aware intervals, exclusions, primary citations and next steps.

## Numerical and delivery evidence

The shipped lookup table uses libRadtran 2.0.6, plane-parallel DISORT, eight
streams and 0.5 nm UV sampling. Across 80 withheld atmospheric states, forward
interpolation has 2.76% 95th-percentile and 3.21% maximum absolute relative error
for reference UVI at least 1. SW inversion with different SW/UV albedos gives
1.66% and 1.97%. Maximum forward absolute error across all states is 0.248 UVI.
These test interpolation of the selected physics, not observational truth.

An initial pseudo-spherical configuration was rejected because thick-cloud,
low-sun states violated energy conservation. The shipped table and builder use
explicit plane-parallel energy checks. Low-sun approximation and scalar cloud
extensions remain flagged. The table identity, reference assumptions and rebuild
process are in [the table record](analysis/TABLE_PROVENANCE.md).

The daily export has a versioned schema and explicit local dates, rolling-peak
semantics, spatial support, freshness, quality flags and unavailable values.
A complete archived-input replay produced 54 town/elevation entries for two days
in approximately 17 seconds, using 242 MiB peak RSS. This is a local deterministic
replay benchmark, not a live-service availability measurement. See the
[data interface](analysis/PRODUCT_DATA_INTERFACE.md) and
[product contract](analysis/PRODUCT_CONTRACT_V1.md).

All 110 repository tests passed at the measurement-assessment checkpoint.
Independent checks reconciled 14,129 unique observed UV windows, 92 Payerne
rolling peaks, 3,462 accepted daily method rows, 6,516 summary values and 85,950
native values. Separate full-field decoding checked 95 values across four ICON
archive configurations. The existing netCDF4/NumPy binary-size import warning
was recorded; numerical and NetCDF round-trip tests passed without masking it.

## Retained scientific history

Each study has its own scope. Earlier counts and conclusions describe that
milestone; they are not additional independent cases to add to the latest total.
In particular, Payerne was metadata-only before its separately frozen adapter
was qualified for provisional scoring.

| Study | Retained record |
|---|---|
| Expanded three-cycle and observation-driven diagnostics | [Protocol](analysis/SCIENTIFIC_PLAN.md), [findings](analysis/FINDINGS.md) |
| 150-date, 135-station shortwave and historical Davos UV | [Protocol](analysis/MULTIYEAR_PLAN.md), [findings](analysis/MULTIYEAR_FINDINGS.md) |
| Daily product and independent-site reservation | [Contract](analysis/PRODUCT_CONTRACT_V1.md), [findings](analysis/PRODUCT_FINDINGS.md) |
| Additional 72 RT stress cases and complete delivery replay | [Readiness assessment](analysis/PRODUCT_READINESS_ASSESSMENT.md) |
| Broader Swiss measurement assessment | [Protocol](analysis/SWISS_UV_PROTOCOL.md), [findings](analysis/SWISS_UV_FINDINGS.md) |

Detailed generated reports, plots, raw pairs, notebooks and input hashes remain
in their local `work/` study directories. The initial top-level JSON reports and
one-day notebook are retained in `work/initial-validation-20260905/`; their
removal from Git does not discard the evidence. A source snapshot preceding
cleanup is in `work/repository-cleanup-20260906/source-before/`.

## Reproduce

```sh
uv sync --locked --extra cams --group analysis
uv run --no-sync pytest -q
uv run --no-sync python -m icon_uv.check_grid --grid work/uv.nc --output work/grid_check.json
```

The final command requires a previously generated UV grid. Full observational
replay needs the retained local archives and authorized source access; ordinary
tests need neither. See [analysis/replay instructions](analysis/README.md) and
[artifact policy](CONTRIBUTING.md). Freshly rebuilding RT references additionally
requires the external libRadtran installation and its data.
