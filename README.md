# icon-uv

A small offline ICON/CAMS UV diagnostic for Switzerland. Ordinary Python
functions and one CLI; no server, scheduler, database, model plugin or frontend.

**Experimental scientific software.** Numerical RT checks are not validation
against measured UV. This package must not be presented as an official or
operationally qualified UV forecast.

The real-data prototype runs 38,718 cells × 24 hours in about 52 seconds on the
tested Mac. Numerical checks pass, but an exploratory measurement comparison
shows substantial mountain-site overprediction. See [VALIDATION.md](VALIDATION.md)
before interpreting these fields as forecast guidance.

## Install

```sh
git clone https://github.com/ofuhrer/icon-uv.git
cd icon-uv
uv sync --extra cams
uv run pytest -q
uv run icon-uv --help
```

Or install the directory with `uv pip install '.[cams]'`. The `cams` extra is only
needed for downloading from ADS. Runtime dependencies are NumPy, SciPy, xarray,
netCDF4, requests and ecCodes. No libRadtran executable is needed at runtime: a
small generated radiation table ships with the package. The lockfile pins the
tested environment; NumPy is constrained below 2.4 pending upstream NetCDF
compatibility. A known netCDF4 import warning can occur under pytest's warning
capture; it is not suppressed here. NetCDF round-trip tests check actual values,
time bounds and integer flags.

## Real-data run

Default domain: **5.3–11.2°E, 45.2–48.4°N**, all Switzerland plus approximately
50–80 km beyond its geographic extremes. Output uses the native ICON-CH2 cell
centres and retains original cell indices/grid UUID, not a newly interpolated
high-resolution grid. The demonstrated subset has **38,718 cells**.

The following reproducible cycle covers 6 September 2026, midnight to midnight
Europe/Zurich (5 September 22 UTC through 6 September 22 UTC). ICON's public
files expire quickly; use another available cycle and appropriate boundary leads
for a new live download. Retain the subset files for offline replay.

```sh
uv run icon-uv fetch-icon \
  --reference 2026-09-05T12:00:00Z --first-lead 10 --last-lead 34 \
  --output work/icon.nc

uv run icon-uv fetch-cams \
  --reference 2026-09-05T00:00:00Z --first-lead 21 --last-lead 48 \
  --output work/cams.grib

uv run icon-uv run --icon work/icon.nc --cams work/cams.grib \
  --output work/uv.nc
```

CAMS is openly licensed but ADS requires your own free account, dataset licence
acceptance and `~/.cdsapirc`; follow the [official setup instructions](https://ads.atmosphere.copernicus.eu/how-to-api).
Never put a key in this project. ICON downloads are anonymous via public STAC;
short-lived signed asset URLs are neither logged nor retained in provenance.

`first-lead` and `last-lead` are **interval boundaries**, not a count of forecasts.
The example 10..34 produces 24 intervals. The initial implementation fetches the
control member only; it does not manufacture an ensemble from deterministic data.
The kernel can be called separately on other members after their inputs are
normalized to the same contract.

## What is calculated?

1. Download ICON `ASOD_S`, surface pressure, broadband albedo and snow fraction;
   select the native-grid subdomain. Recover hourly SW means from forecast-start
   means, propagating GRIB packing tolerance. Average surface-state endpoints.
2. Read one CAMS cycle's **total-column ozone** and **AOD550**. Convert ozone from
   kg/m² to DU, interpolate composition bilinearly in space and linearly in time.
   Reject missing coverage, gaps over three hours, later-than-ICON cycles or
   cycles more than 36 hours older. The CAMS time series must bracket the ICON
   interval midpoints. This cycle rule prevents initialization look-ahead; actual
   dissemination latency must also be checked for historical forecast evaluation.
3. Infer an effective cloud optical thickness matching ICON's hourly shortwave
   mean. Evaluate a spectral-RT-derived table over four solar midpoint samples
   per hour and integrate erythemal UV. These are **not new subhourly cloud forecasts**.
4. Emit hourly UV fields, source state and quality flags in a compressed NetCDF.

The table was generated with libRadtran 2.0.6, plane-parallel DISORT with eight
streams, 0.5 nm UV sampling and Kato2 broadband radiation. Resolved irradiance is
multiplied by the erythema action spectrum **before** spectral integration.
The runtime interpolates total/direct flux in log space and computes diffuse by
subtraction. Ozone uses log coordinates and cloud optical thickness log(1+tau).
Plane-parallel geometry is a deliberate low-sun approximation, flagged whenever
an interval includes a daylight solar sample above 78° zenith. The initial
pseudo-spherical configuration failed an energy-conservation check for thick
cloud at low sun and was discarded; see the validation report.

The shipped table supports ozone 200–500 DU, pressure 500–1050 hPa, AOD550 0–1,
albedo 0–0.85 and effective cloud optical thickness 0–150. Inputs outside those
bounds stop the calculation; extreme composition or higher surface albedo needs
a qualified table extension, not clipping. Atmospheric profiles, water vapour
and aerosol optical type are fixed assumptions, as listed below.

### Output contract

Variables indexed by `time,cell` include:

- `uvi`, `clear_sky_uvi`: dimensionless, hourly mean, open-horizon horizontal.
- `erythemal_direct`, `erythemal_diffuse`: W/m², hourly mean; direct is horizontal,
  not direct normal. `uvi = 40 * (direct + diffuse)`.
- `uvi_sample_max`: maximum reconstructed solar sample within the hour, not an
  observed or explicitly forecast subhourly cloud maximum.
- `effective_cloud_tau550`, `cloud_scale`, `quality_flag`.
- Pressure, ozone, AOD, snow and surface albedo, plus the original hourly SW
  forcing, so a POI can be recomputed without another network call.

Coordinates include latitude/longitude, model altitude and original cell index.
`time` is the UTC interval midpoint; `time_bounds` is authoritative. Attributes
record ICON and CAMS cycles, sources/hashes, RT configuration/table hash and package version.
Cell centres and grid identity are retained; this is not a self-contained UGRID
mesh with triangle vertices. Use the source ICON grid if polygon geometry is needed.

Flags are bit masks, not exclusive categories:

| Bit | Meaning |
|---:|---|
| 1 | SW exceeds the clear-sky calculation; explicitly flagged scalar extension |
| 2 | SW below the minimum cloud-table response; explicitly flagged scalar extension |
| 4 | Weak/no solar signal, cloud inversion uninformative |
| 8 | Nonmonotonic cloud response; earliest bracket selected |
| 16 | Approximate local atmospheric-column adjustment at a POI |
| 32 | Approximate terrain screening, not a complete exposure calculation |
| 64 | Daylight solar sample above 78° zenith; plane-parallel approximation |

An unset flag does **not** certify observational forecast accuracy. Missing or
out-of-table atmospheric inputs fail explicitly rather than being silently clipped.

## Optional POI API: the caller supplies the local information

There is deliberately no elevation service or automatic horizon/snow lookup.
Every POI must specify latitude, longitude, altitude, UV albedo, and a complete
horizon. An all-zero horizon is an explicit caller assertion of an open horizon.

```python
import xarray as xr
from icon_uv.products import POI, compute_pois

# Demonstration geometry, NOT surveyed conditions at Payerne.
site = POI(
    name="example",
    latitude=46.8156,
    longitude=6.944,
    altitude_m=491,
    horizon_degrees=(0.0,) * 36,  # azimuths 0,10,...,350°, north clockwise
    uv_albedo=0.05,
)
with xr.open_dataset("work/uv.nc") as grid:
    points = compute_pois(grid.load(), [site])
```

The equivalent CLI takes a JSON list of the same fields:

```sh
uv run icon-uv poi --grid work/uv.nc --locations my-pois.json --output work/pois.nc
```

`examples/davos.json` is an executable example of caller-owned local data. Its
1588.2 m altitude and 72 horizon samples were extracted from swisstopo terrain
profiles through [geo.admin.ch](https://api3.geo.admin.ch/rest/services/profile.json)
on 5 September 2026 (20 km radius, 401 samples/ray, 5° azimuth spacing, horizons
rounded to 0.01°). The UV albedo 0.05 is an explicit example assumption. This is a
study point, not a surveyed instrument installation or a measured albedo. The API
does not obtain any of these local inputs itself.

`horizon_degrees` must contain at least four equally spaced azimuth samples from
north, with elevations between 0 and 90°. The complete supplied geometry is
recorded in the output. POIs more than 10 km from a source cell are rejected by
default. No interpolation outside the forecast coverage is performed.

Pressure is adjusted from the nearest cell using an 8434 m scale height; ozone,
AOD and effective cloud are retained. POI UV is recomputed at that pressure,
local albedo and solar geometry. This does **not** determine whether a summit
lies above cloud. Large elevation differences and valley inversions need a more
complete column model before this can be treated as an accurate local forecast.
The API rejects a radiation table different from the one used for the grid;
recompute the grid after changing the table.

`terrain_screened_uvi` is separate from ambient `uvi`. It blocks the direct beam
at the horizon and scales diffuse radiation by the isotropic horizontal sky-view
factor. It omits anisotropic diffuse light and reflections from surrounding
terrain/snow. Do not interpret shadow as zero exposure or as a protection guarantee.

## Validation and rebuilding

```sh
uv run pytest -q

# Cheap per-run integrity check, including a seeded sample of SW reconstruction.
uv run python -m icon_uv.check_grid --grid work/uv.nc --output work/grid_check.json

# Developer workflow only; libRadtran must already be installed at this path.
uv run icon-uv build-table --lib /path/to/libRadtran-2.0.6 \
  --cache work/rt-cache --output icon_uv/data/rt.npz

uv run python -m icon_uv.validate --table icon_uv/data/rt.npz \
  --lib /path/to/libRadtran-2.0.6 --cache work/rt-cache \
  --output work/rt_validation.json
```

The numerical validator uses a fixed, recorded seed and withheld atmospheric
states, not the lookup nodes. It checks forward interpolation and the complete
SW-inversion-to-UVI path. Input handling, night behaviour, interval accounting,
chunk consistency, POI contracts and serialization have separate synthetic tests.
The numerical interpolation gate is ≤5% at the 95th percentile and ≤10% maximum
relative error for reference UVI ≥1, for both paths; failure gives a nonzero exit
status. These are engineering thresholds, not an observational accuracy promise.
See `VALIDATION.md` for actual results and limitations of the real-data run.

Keep the per-run input checks and quality flags when integrating with DWH/Ninjo
or another product framework. That framework can build maps, local-day summaries
and POI displays from the base fields; it must retain interval semantics and not
call the maximum of hourly means an instantaneous daily maximum. No permanent
high-resolution display grid is needed in the radiation calculation itself.

One-time numerical qualification is insufficient for operations: retain source
age/completeness checks, flag-frequency tracking and periodically matched
observations, with requalification after model/table/input changes. The package
provides integrity checks and an observation-comparison function, not a monitoring
service or an operational acceptance threshold. In particular, low-sun, snow,
high-altitude and unusual aerosol regimes remain scientifically unqualified.

For independent observations use `compare_observations(forecast, observations)`:
both must have matching hourly bounds and named POIs; observations supply `uvi`
in units `1` and boolean `qc_good`. It returns matched-sample bias/MAE/RMSE without
fitting or calibration. This small API is not a substitute for seasonal/regime
verification, instrument calibration or an agreed observation delivery contract.

## Deliberate limits

- Fixed midlatitude-summer reference profile, 20 mm water vapour, aerosol Ångström
  exponent 1.3, SSA 0.95 and asymmetry 0.7. CAMS AOD varies, but its aerosol type
  and vertical distribution are not yet used. Dust/smoke accuracy is unqualified.
- Pressure-equivalent reference height; no detailed ICON model-level cloud column.
- Uniform effective liquid cloud at 1–2 km above that reference surface. Broken
  cloud, ice cloud and subhourly variability cannot be reconstructed uniquely.
- UV albedo `0.05 + 0.75 * snow_fraction` is experimental, not a measured UV albedo
  or a validated regional snow-reflection model. POIs must provide their own value.
- NOAA approximate solar geometry; 89–90° zenith tail faded to zero; no twilight
  prediction. Plane-parallel RT is unqualified at low sun (flag 64).
  Radiation evaluated at 1 AU is scaled by Earth–Sun distance.
- Control-run gridded output only in the public downloader. No ensemble
  calibration, forecast scheduler, monitoring daemon, public-health advice,
  customer templates or deployment framework is included.

## Sources and attribution

- [MeteoSwiss ICON open-data documentation](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model),
  [STAC collection](https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-forecasting-icon-ch2).
  Source: MeteoSwiss; retain attribution when redistributing extracts/results.
- [CAMS global atmospheric composition forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts),
  produced by ECMWF for Copernicus. Retain the dataset's attribution/licence terms.
- [libRadtran](https://www.libradtran.org/): optional GPL-licensed reference solver;
  its executable and upstream atmospheric/spectral data are not vendored here.
- [SACRaM open-data status](https://opendatadocs.meteoswiss.ch/b-data-atmosphere/b6-sacram):
  observations were marked not yet available when checked on 5 September 2026.

The generated table and files remain scientific approximations. Neither the
package nor the upstream data providers warrant individual exposure advice.
