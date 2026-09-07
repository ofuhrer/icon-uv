# Changelog

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
