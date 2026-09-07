# Calculation method

icon-uv estimates erythemal UV irradiance from broadband shortwave radiation,
atmospheric composition and surface conditions. It uses a precomputed radiation
table at runtime, then derives hourly fields, point forecasts and daily peaks.

## ICON and CAMS inputs

ICON `ASOD_S` is the mean downward shortwave flux since forecast initialization.
For consecutive forecast leads `t₀` and `t₁`, hourly flux is recovered as:

```text
SW_hour = (t₁ × SW_mean(t₁) − t₀ × SW_mean(t₀)) / (t₁ − t₀)
```

GRIB packing uncertainty is propagated through this difference. Significant
negative energy is rejected. Surface pressure, broadband albedo and snow
fraction are averaged over the two interval endpoints. Downloads select all 21
ICON-CH2-EPS members by default, preserving member, native-cell and grid identities.
Use `fetch-icon --control` for CTRL only. Missing samples remain unavailable;
the default minimum coverage is 90%.

CAMS supplies total-column ozone and aerosol optical depth at 550 nm. Ozone
is converted from kg/m² to Dobson units. Composition is interpolated bilinearly
in space and linearly in time to ICON interval midpoints. The input series must
bracket those midpoints, have gaps no greater than three hours, and cover the
ICON cells. The CAMS cycle must precede or equal ICON initialization and be no
more than 36 hours older.

`fetch-cams` writes normalized NetCDF with `ozone_du` and `aod550` on
`(time, latitude, longitude)`, together with the forecast reference time, ADS
request and source GRIB hash. The temporary download is removed after conversion.
Both input filters produce normalized NetCDF; subsequent UVI computations use
these files independently of the upstream data formats.

## Radiation lookup table

The bundled table was generated with libRadtran 2.0.6 using plane-parallel
DISORT, eight streams, 0.5 nm UV sampling and Kato2 broadband radiation.
Spectral UV irradiance is weighted by the erythema action spectrum before
integration. Stored components are horizontal shortwave and erythemal
irradiance, split into direct and diffuse fluxes, at 1 AU.

| Coordinate | Supported range |
|---|---|
| Solar zenith angle in the lookup table | 0–89° |
| Total ozone | 200–500 DU |
| Surface pressure | 500–1050 hPa |
| AOD550 | 0–1 |
| Surface albedo | 0–0.85 |
| Cloud optical thickness at 550 nm | 0–150 |

Flux interpolation uses logarithmic total/direct irradiance; diffuse is the
difference between total and direct. Ozone coordinates are logarithmic and
cloud thickness uses `log(1 + tau)`. Other coordinates use linear interpolation.
Out-of-range atmospheric or surface inputs raise errors.

The reference atmosphere is AFGL midlatitude summer with 20 mm water vapour.
Aerosol Ångström exponent is 1.3, single-scattering albedo 0.95 and asymmetry
parameter 0.7. An effective liquid cloud with 10 μm droplet radius lies 1–2 km
above a pressure-equivalent surface. That reference height is
`max(0, -8434 × log(pressure / 101325))` metres.

## Cloud inference and UV Index

For each hour, solar geometry is sampled at evenly spaced midpoints. The model
finds an effective cloud optical thickness whose table shortwave flux matches
the ICON hourly mean. Four samples per hour are the default; `compute_grid`
accepts a `samples` argument, with twelve useful for daily five-minute sampling.

Broadband albedo is used for the shortwave fit. UV is then evaluated with
`uv_albedo = 0.05 + 0.75 × snow_fraction`. Point calculations can instead supply
an explicit UV albedo. If the cloud response is nonmonotonic, inversion chooses
the earliest bracketing branch. Shortwave above clear sky or below the minimum
cloud response uses a scalar extension and sets a quality flag.

The inferred thickness represents the radiative effect of clouds; it does not
uniquely identify cloud fraction, height or phase. The table accounts for the
different spectral response of shortwave and UV. Its homogeneous liquid-cloud
approximation cannot resolve subhourly cloud variability or three-dimensional
cloud-edge enhancement, and is sensitive to ice clouds over bright snow. See
[validation](validation.md#cloud-conversion-and-numerical-accuracy) for the evidence
and its coverage.

UV Index is calculated from erythemal direct and diffuse irradiance:

```text
UVI = 40 × (erythemal_direct + erythemal_diffuse)
```

Earth–Sun distance scales the table's 1-AU irradiance. Solar geometry follows
the NOAA approximation with leap-year handling. Zenith angles above 78° set a
low-sun flag; the response fades to zero between 89° and 90°, with zero at night.

Hourly output integrates the within-hour samples. Daily output reconstructs
five-minute solar evolution from each saved hourly cloud state and selects
30-minute rolling peaks. Regional output aggregates those cell peaks spatially.
These calculations run independently for each ensemble member. Daily products
then take the ensemble median and retain quantiles and threshold frequencies;
CAMS composition and the radiation physics remain common to all members.
See [daily products](daily-products.md) for exact support and rounding rules,
and [point forecasts](outputs.md#point-forecasts) for local geometry adjustments.

## Accuracy and checks

The numerical validator compares interpolation and SW-to-UV inversion against
withheld direct-solver states. Grid integrity checks independently reconstruct
shortwave from the saved cloud state. Observation comparisons use matched time
support and retain exclusions for missing data or instrument metadata.

[Validation results](validation.md) report numerical errors, Swiss-site daily
peak errors and sensitivity to spatial matching. [Table rebuilding](https://github.com/ofuhrer/icon-uv/blob/main/CONTRIBUTING.md#change-the-radiation-table)
describes the packaged table identity and reference-cache inputs.
