# ICON/CAMS UV prototype: validation record

Run date: 5 September 2026. Scope: implementation and numerical qualification of
variant C, **not operational or observation-based forecast qualification**.

Outcome: the offline native-grid implementation is computationally feasible and
passes numerical/data-integrity checks. The exploratory mountain-site comparison
does **not** support operational forecast qualification. Retain the prototype as
a reproducible evaluation basis, not a validated public UV service.

Final results below use the corrected plane-parallel table. The rejected initial
configuration and the reason for replacing it are documented below.

## Data and execution

The public ICON-CH2 control forecast initialized **2026-09-05 12 UTC** supplies
ASOD_S, PS, ALB_RAD and SNOWC at boundary leads 10–34. The downloaded native-grid
subset contains **38,718 cells**, bounded by **5.3–11.2°E, 45.2–48.4°N**. It covers
all Switzerland plus roughly 50–80 km beyond its geographic extremes. Native
cell indices, coordinates, altitude and grid UUID are retained. No metre-scale
radiation grid or interpolation to an artificial weather resolution is involved.

The 24 hourly intervals span **5 September 22 UTC to 6 September 22 UTC**: the
complete local day of 6 September in Europe/Zurich. ASOD_S is decoded as a mean
since forecast initialization, not an instantaneous or already-hourly flux.
Differencing propagates GRIB packing tolerance and rejects significant negative
hourly energy. Surface states are averaged over the two interval endpoints.

CAMS composition uses the **2026-09-05 00 UTC** forecast, leads 21–48 every three
hours, from ADS: total-column ozone and total AOD550. The buffered composition
domain is larger than the ICON subset. The GRIB file's SHA-256 is
`a8ae0bdc0abfa0f09ef02014e7efaa35546b1160c13f68d267468d3287b26eb5`.
Ozone is converted from kg/m² to DU. Composition is interpolated to interval
midpoints and cell centres, with no spatial or temporal extrapolation.

ICON asset identifiers/hashes and CAMS cycle/hash accompany the output. The
local ADS configuration is outside the repository and has mode 0600; no API key
belongs in an output or provenance record. The demonstrated CAMS cycle precedes
ICON initialization by 12 hours. This is not a historical dissemination-latency
backtest; a proper backtest must use data actually available at issue time.

## A validation failure that changed the implementation

The first table used pseudo-spherical DISORT. Comparison against withheld
calculations using that same configuration looked satisfactory, but inspection
of real-run quality flags revealed an unphysical thick-cloud tail at low sun.
At one reference state (75° zenith, 280 DU, 900 hPa, AOD 0.1, albedo 0.1,
cloud tau 150), it returned about **11,230 W/m²** downward shortwave.

The original table had 845 of 10,368 nodes exceeding a conservative solar
energy bound. This was a failure of that configuration, irrespective of whether
interpolation reproduced it. Its table and numerical qualification were rejected.
No general claim that all pseudo-spherical solvers/configurations fail follows.

The replacement uses **plane-parallel DISORT**, with an independent check at
every generated node: `(1 - albedo) * downward_SW <= 1400 * cos(SZA)` W/m² at
1 AU. This is a conservative energy bound for the adopted plane-parallel,
Lambertian solar calculation, not a criterion for arbitrary 3-D irradiance.
The problematic example then gives about **8.95 W/m²**.

A separate inversion bug was fixed: testing only the thickest-cloud endpoint
could override a valid thinner-cloud solution when the response was nonmonotonic.
The lower extension now uses the minimum response over all cloud nodes; valid
solutions use the earliest bracketing branch. A regression test covers both a
rising tail and the previously possible conflicting high/low classification.

The geometry trade-off is explicit. In illustrative stable reference comparisons,
plane-parallel clear-sky UVI was lower than pseudo-spherical UVI by 0.22% at 35°
zenith, 1.67% at 65°, 5.22% at 78° and 15.4% at 85°. Those are sensitivity examples,
not an error envelope or an independent truth comparison. Daylight samples above
78° set bit 64; 89–90° is faded to zero and twilight is not predicted.

## Numerical qualification

**29 tests pass**, including interval/packing semantics, units, missing coverage,
night handling, table bounds and energy conservation, cloud branch selection,
chunk consistency, POI requirements/table identity, NetCDF round trips and atomic
publication failure. One known netCDF4 import warning remains under pytest:
`numpy.ndarray size changed`. It is not suppressed. Actual values, timestamps and
integer flags round-trip correctly; the environment also passes `uv pip check`.
See the [upstream issue](https://github.com/Unidata/netcdf4-python/issues/1354).

Tested environment: macOS 26.6.2 arm64, Python 3.12.12, NumPy 2.3.5, SciPy 1.18.1,
xarray 2026.7.0, netCDF4 1.7.4, ecCodes 2.48.0, cdsapi 0.7.7 and pytest 9.1.1.
The lockfile records dependency resolution. The wheel was installed and exercised
in an isolated uv environment outside the project: it includes the 201,687-byte
table and obtains ecCodes from the Python binary package, not a Homebrew install.

The final 24-hour native-grid calculation took **50.2 seconds in the kernel,
51.91 seconds end-to-end**, with **325,238,784 bytes (310 MiB) peak RSS**, measured
with `/usr/bin/time -l` on this Apple-silicon Mac. This includes local loading and
compressed output, not remote downloads or table generation. It is a single
control-run/day benchmark, not a full-ensemble or operational throughput SLA.
The output is **21,943,275 bytes (21.9 MB)**, including replay state and provenance.

The final table SHA-256 is
`a33db2d4b2806f216eef356c761460383bb4a9fca53e3b958715bc12e6d6dcba`.
The [grid integrity report](grid_check.json) passes: 512 seeded cells across the
day provide 6,656 non-weak-signal hourly reconstruction checks. Maximum SW
residual is **0.0000472 W/m²**; maximum UVI/component identity residual is
**0.000000954 UVI**. UVI ranges from 0 to 10.315 in this experimental forecast.

Flags over 929,232 cell-hours are not mutually exclusive:

| Flag | Cell-hours | Interpretation |
|---|---:|---|
| Above clear-sky SW | 26,172 | Scalar extension, not resolved 3-D cloud enhancement |
| Below cloud-table minimum | 0 | No lower extension needed in this run |
| Weak/no solar signal | 425,898 | Mostly night; cloud fit is uninformative |
| Nonmonotonic response | 1 | Earliest bracket, explicitly flagged |
| Low-sun plane-parallel approximation | 142,338 | All have UVI below 1 in this run |

The earlier 119,389 below-thickest-cloud flags disappeared after correcting the
solver and branch selection. These frequencies are a diagnostic baseline, not
automatic operational acceptance limits.

The [numerical report](validation.json) passes all gates on **80 withheld states**
(57 with reference UVI at least 1; seed 20260905):

| Calculation | 95th percentile absolute relative error | Maximum absolute relative error |
|---|---:|---:|
| Forward table interpolation | 2.76% | 3.21% |
| SW inversion, equal SW/UV albedos | 1.12% | 1.43% |
| SW inversion, different SW/UV albedos | 1.66% | 1.97% |

The maximum absolute forward difference across all 80 states is 0.248 UVI.
For three spectral/stream checks, changing 0.5 nm to 0.25 nm changes UVI by
0.105–0.193%; changing eight to sixteen streams changes it by at most 0.0091%.
Illustrative true-water-column cases of 10 and 40 mm, inverted using the fixed
20 mm table, produce UVI errors of +1.57% and −2.99%. This illustrates a structural
assumption error separate from interpolation accuracy; it is not a complete
water-vapour or aerosol sensitivity envelope.

The deterministic validator samples atmospheric states away from lookup nodes,
including clear sky, pressure, ozone, aerosol, snow-like albedo and cloud optical
thickness. The fixed seed makes this a reproducible regression/qualification set,
not a blind observational test. It checks forward UVI interpolation, shortwave
inversion followed by UVI, and inversion with different SW and UV albedos.

The engineering gates are a 95th-percentile relative error of at most 5% and a
maximum of at most 10%, for reference UVI at least 1. The absolute-error result
also includes low-UV cases. These gates assess interpolation of the chosen
physics, not the realism of its fixed profile, cloud or aerosol assumptions.

The grid check independently reconstructs the original hourly shortwave forcing
from the saved effective cloud/scaling state, using a seeded selection of cells
and the same four within-hour solar samples. Weak-signal inversions are excluded
from that identity because they deliberately carry no informative cloud fit.

## Cross-model check and observations

The [CAMS comparison](cams_comparison.json), restricted to CAMS reference hourly
mean UVI at least 1, gives:

| Quantity/region | Matched cell-hours | Mean difference, UVI | MAE, UVI |
|---|---:|---:|---:|
| All-sky, all cells | 343,995 | −0.012 | 0.283 |
| All-sky, below 800 m | 193,807 | −0.069 | 0.246 |
| All-sky, above 2000 m | 47,727 | +0.284 | 0.428 |
| Clear-sky, all cells | 349,195 | +0.063 | 0.200 |
| Clear-sky, above 2000 m | 48,446 | +0.206 | 0.322 |

The separate CAMS UV reference file contains hourly instantaneous `uvbed` and
`uvbedcs` (parameter IDs 214002/214003), from the same 00 UTC cycle. The comparison
uses the trapezoidal average of hourly endpoint values, whereas this package
integrates four solar samples with one ICON-inferred cloud state per hour.
ECMWF's UV documentation defines these as erythemal dose rates in W/m², converted
to UVI by 40; the actual GRIB unit string is `~`. The comparison makes this
parameter-specific override explicit rather than applying it to generic fields.

CAMS is **not independent observational truth**: this calculation shares CAMS
composition, and the two forecasts have different cloud fields, terrain heights,
profiles and albedos. Similar values cannot establish forecast accuracy, and a
single forecast day says little about snow, winter, smoke or broken-cloud skill.

No calibrated, QC-qualified observation validation was completed. When checked on
5 September, [SACRaM's open-data documentation](https://opendatadocs.meteoswiss.ch/b-data-atmosphere/b6-sacram)
said data was not yet available. The current-measurement links from
[PMOD/WRC](https://www.pmodwrc.ch/weltstrahlungszentrum/wcc-uv-2/wcc-uv_measurements/)
returned HTTP 403. No access restriction was bypassed.

An additional, accessible route was found through the
[Austrian UV network](https://www.uv-index.at/about/), which includes Swiss partner
stations. Its [public API](https://uv-data.i-med.ac.at/public/) supplies timestamped
`UV-Index` measurements. A separate ICON run initialized **5 September 00 UTC**,
boundary leads 4–18, and CAMS initialized **4 September 12 UTC** were retrieved
for an exploratory comparison with measurements on **5 September**, not the
still-future 6 September demonstration day.

The [quality notebook](observation_quality.ipynb) and
[saved profile](observation_quality.json) establish the comparison grain and
limitations. Davos, Weissfluhjoch, Zugspitze and Aosta each have all 16 expected
midday half-hourly slots; Dornbirn has zero of 16 and is excluded from statistics.
The five in-domain series have no duplicate timestamps, negative/nonfinite values
or timestamps outside the requested day. Completeness does not establish calibration.

The API does not supply averaging bounds or per-value QC/calibration metadata.
The comparison therefore explicitly approximates hourly means from pairs at
`:15` and `:45`; it does not invent `qc_good=True`. It uses the nearest unadjusted
native-grid cell and records distance and altitude mismatch, not a POI forecast
with invented local horizon/albedo. These are high-confidence metadata/coverage
limitations with high impact on interpreting forecast accuracy. Their remedy is
an observation delivery agreement, not a statistical correction fitted to this day.

The [exploratory comparison](observation_comparison.json) includes 13 paired hours
per available station. Statistics below use only pairs whose reported mean UVI
is at least 1; positive bias means forecast overprediction:

| Station | Selected hours | Bias, UVI | MAE, UVI | Model minus published site altitude |
|---|---:|---:|---:|---:|
| Davos | 6 | +1.815 | 1.815 | +107 m |
| Weissfluhjoch | 5 | +2.128 | 2.128 | −346 m |
| Zugspitze | 3 | +1.921 | 1.921 | −337 m |
| Aosta | 9 | +0.372 | 0.372 | +6 m |

**This is an adverse validation finding, not evidence of operational readiness.**
The mountainous sites show substantial overprediction, despite a numerically
accurate lookup/interpolation implementation. The sample is too small and its
measurement metadata too limited to assign the discrepancy uniquely to ICON
cloud forecasts, the SW-to-UV approximation, site representativeness, or the
measurements themselves. No bias correction was fitted. A broader, QC-qualified
hindcast with colocated measured shortwave and UV is needed to separate these
causes; a clear-sky/cloudy split and local geometry are especially important.

The package provides an exact-hourly-interval observation comparison API, tested
with synthetic data. Before any operational claim, obtain an agreed, calibrated
UV observation feed and evaluate multiple seasons, forecast leads, elevations,
snow/cloud/aerosol regimes and site geometry. Retain availability/age checks and
ongoing quality monitoring; requalify after relevant model or algorithm changes.

## POI demonstration and scope

`examples/davos.json` supplies all its own local information, including altitude,
72 horizon samples and an explicitly assumed UV albedo. The API never obtains
those values implicitly. It returns ambient horizontal UVI separately from an
approximate terrain-screened field. Grid/table hashes must match for recomputation.
For the 6 September study point, the maximum hourly ambient UVI is **6.758** and
the screening-proxy maximum is **6.535**. These are different quantities and
neither is a measured value or an individual exposure limit.

The terrain output is not a full exposure calculation: diffuse light is treated
as isotropic, surrounding snow reflections are absent, and pressure is adjusted
with a fixed scale height while cloud/composition are retained. The method cannot
tell whether a summit is above cloud. A topographically plausible answer is not
equivalent to a validated mountain forecast.

## Reproduce

Use the fetch/run commands in [README.md](README.md), then:

```sh
uv run pytest -q
uv run python -m icon_uv.check_grid --grid work/uv.nc --output grid_check.json
uv run python -m icon_uv.validate --table icon_uv/data/rt.npz \
  --lib /path/to/libRadtran-2.0.6 --cache work/rt-cache \
  --output validation.json
uv run python -m icon_uv.compare_cams --grid work/uv.nc \
  --cams-uv work/cams_uv_reference.grib --output cams_comparison.json
uv run icon-uv poi --grid work/uv.nc --locations examples/davos.json \
  --output work/davos.nc
```

The separate exploratory measurement comparison is reproducible with:

```sh
uv run icon-uv fetch-icon --reference 2026-09-05T00:00:00Z \
  --first-lead 4 --last-lead 18 --output work/icon_observation_day.nc
uv run icon-uv fetch-cams --reference 2026-09-04T12:00:00Z \
  --first-lead 15 --last-lead 30 --output work/cams_observation_day.grib
uv run icon-uv run --icon work/icon_observation_day.nc \
  --cams work/cams_observation_day.grib --output work/uv_observation_day.nc
curl --fail 'https://uv-data.i-med.ac.at/public/data/?product=uve&start=2026-09-05&stop=2026-09-06' \
  -o work/observations_20260905.json
curl --fail 'https://uv-data.i-med.ac.at/public/sites/' -o work/observation_sites.json
uv run python -m icon_uv.compare_public_uv --grid work/uv_observation_day.nc \
  --measurements work/observations_20260905.json --sites work/observation_sites.json \
  --output observation_comparison.json
```

Runtime needs no libRadtran installation; only rebuilding or direct-reference
qualification does. Public ICON assets expire, so saved normalized inputs are
the replay basis. Fetch a current cycle for a new live demonstration.

Primary references: [ICON data documentation](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model),
[CAMS forecast dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts),
[CAMS UV documentation](https://confluence.ecmwf.int/spaces/CKB/pages/212454117/CAMS%2BGlobal%2Batmospheric%2Bcomposition%2Bforecast%2Bdata%2Bdocumentation),
[libRadtran documentation](https://www.libradtran.org/doc/libRadtran.pdf).
