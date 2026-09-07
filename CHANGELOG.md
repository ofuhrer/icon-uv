# Changelog

## 0.2.0 — 2026-09-07

- Point locations default to forecasts at their requested coordinates and elevation,
  using the same ICON snow-derived UV albedo as regional products unless overridden.
- Hourly and daily calculations share these surface defaults. Local horizon
  screening is optional and demonstrated for one site; town map values remain ambient.
- Schema v5 supports inherited point albedo while preserving schemas v1–v4.
- Fix misleading terrain-screened output for points without a horizon and mixed
  daily catalogs. Update the map example to provide a Zermatt forecast.
- Document the use of ICON's base shortwave flux, separately from its orographically
  shaded radiation diagnostics.

Migration: `PointLocation` and modern point JSON entries now default to
`treatment="adjusted"`. Set `treatment="native"` to retain the previous matching
behavior. Legacy town catalogs and explicit POI overrides remain supported.
Terrain-screened daily catalogs must contain only points with explicit horizons.

## 0.1.0 — 2026-09-07

First public release of icon-uv, a Python package and CLI for calculating UV
Index forecasts from ICON weather and CAMS atmospheric composition.

- Hourly grid and point forecasts using the bundled radiation lookup table.
- Daily JSON products for towns and regions, with ensemble coverage, uncertainty,
  local-day summaries and versioned JSON schemas.
- Shared location definitions for hourly point and daily products, including
  native terrain, adjusted elevations, albedo and horizon shading.
- Normalized ICON/CAMS NetCDF inputs, saved-state validation and input preflight
  checks with actionable errors.
- Corrected regional ensemble coverage, missing-member peak timestamps and
  precision loss when saving boundary albedo values.
- Interactive map example with field selection, uncertainty and degraded-data
  indicators, plus a credential-free offline example.
- Installation and API guides, automated tests and distribution checks, and a
  workflow prepared for PyPI Trusted Publishing.

The package requires Python 3.11 or newer. CAMS acquisition uses the optional
`cams` extra and an ADS account; saved-input calculations need no credentials.
