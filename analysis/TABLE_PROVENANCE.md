# Shipped radiation table

`icon_uv/data/rt.npz` is intentionally versioned. It is a 201,687-byte numerical
runtime dependency, not a downloaded forecast or a per-run result. Shipping it
keeps normal installations independent of libRadtran and avoids regenerating
10,368 reference columns for every user.

SHA-256:
`a33db2d4b2806f216eef356c761460383bb4a9fca53e3b958715bc12e6d6dcba`.

The NPZ embeds its configuration: schema 2; libRadtran 2.0.6; plane-parallel
DISORT with eight streams; 0.5 nm UV spacing; AFGL midlatitude-summer profile;
20 mm water vapour; aerosol Ångström exponent 1.3, single-scattering albedo 0.95
and asymmetry 0.7; effective liquid cloud at 1–2 km above the pressure-equivalent
surface, with 10 μm effective radius. Fluxes are horizontal at 1 AU, with separate
shortwave and erythemal direct/diffuse components.

It was generated and numerically qualified on 5 September 2026, then rechecked
with strengthened reference-cache provenance on 6 September. The original table
metadata predates executable/data content hashes; those are available in the
later local reference-validation reports. Do not imply that later metadata was
embedded in the original table. The rejected pseudo-spherical table remains a
local investigation artifact and is not shipped.

Numerical interpolation results are summarized in [validation status](../VALIDATION.md).
Scientific observations and the 72 additional physical stress cases assess
limitations beyond interpolation. No new table was fitted to those outcomes.

Build candidates without overwriting the shipped table:

```sh
uv run icon-uv build-table --lib /path/to/libRadtran-2.0.6 \
  --cache work/rt-cache --output work/candidate_rt.npz
uv run python -m icon_uv.validate --table work/candidate_rt.npz \
  --lib /path/to/libRadtran-2.0.6 --cache work/rt-cache \
  --output work/candidate_rt_validation.json
```

Before replacing the package data, retain the candidate configuration, input/
solver identities, numerical checks and independent product comparisons. Review
the change, update this record and rebuild grids using the new identity. Exact
table identity is part of the grid/POI/daily-export contract. The upstream solver
and its data are external; their licensing and attribution are separate from the
generated table and must be respected if redistributed.
