# Product contract v1 — fixed before daily-product scoring

6 September 2026. This is the project's explicit working contract, not a claim
to reproduce the undocumented implementation of the attached MeteoSwiss map.

## Quantity and time

- Primary quantity: daily maximum of a 30-minute mean ambient horizontal
  all-sky UVI, evaluated at five-minute window starts. Each window's modeled
  mean uses six five-minute midpoint samples. This resolves solar evolution;
  cloud optical depth/scale remain constant within each native hourly interval.
  The output explicitly names this temporal reconstruction. It cannot recover
  actual subhourly cloud evolution or guarantee the exact continuous peak.
- Report the maximum of native hourly means as a separate temporal-resolution
  diagnostic. Compare both with observed 30-minute means on the same five-minute
  window grid. Do not call the historical 08–16 UTC maximum a full-day maximum.
- Valid days are Europe/Zurich calendar dates, with timezone-aware UTC bounds
  across both daylight-saving transitions. Today and tomorrow are relative to
  the explicitly supplied UTC issuance time, never the machine's current date
  during replay. Output UTC source and peak-window timestamps.
- Require every native hourly interval intersecting daylight at a requested
  cell. Determine daylight using one-minute solar samples and include the
  containing full hour. Night-only missing intervals are not missing daylight.
  Maxima use all complete 30-minute windows within the local day, with modeled
  nighttime UVI zero. An absent daylight driver makes that cell/day unavailable;
  do not select a maximum from the remaining hours. Reject overlapping intervals,
  mismatched time labels, negative/nonfinite drivers and unsupported table inputs.
- For observations require bracketing samples and the frozen cadence limits
  (30 s for nominal 10 s, 75 s for nominal 60 s), throughout daylight. Integrate
  raw irradiance piecewise-linearly; no missing-to-zero replacement in daylight.
  Record excluded days rather than selecting only their complete peak windows.

## Display and categories

- Keep unrounded UVI; display `floor(UVI + 0.5)` for finite nonnegative values.
  Half-integers round upward, not Python's ties-to-even rule. Round only after
  temporal/spatial aggregation. Values above 11 remain available numerically.
- Category is a deterministic function of the displayed integer: 0–2 low,
  3–5 moderate, 6–7 high, 8–10 very high, >=11 extreme. Missing has no displayed
  number and no category. Zero is legitimate and is distinct from unavailable.
  Also report raw threshold-crossing diagnostics to expose rounding sensitivity.

## Spatial support

- Towns use a named, versioned coordinate/elevation catalog, selecting the
  nearest native cell within 5 km and 300 m of target elevation. Return both
  target and source coordinates/elevations and their differences. If no suitable
  cell exists, return unavailable; do not invent a cloud profile above terrain.
- Mountain-region entries use caller-defined geographic bounding boxes and
  native terrain cells within +/-200 m of 1000, 2000 or 3000 m. Report the 90th
  percentile of cell daily maxima, with median/range and selected/valid counts.
  This is a representative upper regional value, not an area mean, a single
  peak at one instant, or an official regional forecast definition. At least
  five unique native cells and >=95% valid selected cells are required; any
  incomplete support is labelled degraded. Below that coverage, unavailable.
- Native cells retain their own cloud, pressure and surface state. The product
  does not vertically transplant a valley cloud column to 3000 m. It does not
  infer personal exposure or terrain-screened values. Example boxes/catalog
  entries must be labelled illustrative, not official boundaries or station data.

## Identity and reliability

- Versioned JSON output contains contract version/hash, issue time, valid date,
  location identity/support, raw and displayed UVI, category, source cycles and
  hashes, peak definition, quality reasons and scientific qualification scope.
- Initial working freshness limits at issuance: ICON cycle <=24 h old, CAMS
  cycle <=48 h old; future source cycles are invalid. These are transparent
  project defaults, not a statement about actual publication/availability SLA.
  Stale source inputs produce unavailable entries, not silently reused values.
  A source reference time alone does not prove historical delivery latency.
- No automatic fallback in v1. Keep last successful output intact on generation
  failure with atomic replacement. Explicit unavailable entries are valid JSON;
  NaN/Infinity and inconsistent category/number combinations are forbidden.
- Separate data quality from scientific qualification. Complete inputs do not
  imply validated regional skill. Experimental temporal and snow assumptions
  remain in provenance even when structural reliability checks pass.

## Validation fixed before scoring

- Preserve the original 150-date roster and prior frozen studies. Acquire new
  native boundaries 03–21 and 27–45 h and CAMS leads 12–60 h from the previous
  day's 12 UTC cycle in a separate work directory. Verify the daylight coverage
  rule for every site/date rather than assuming those ranges always suffice.
- Primary historical UV comparison is at the fixed WOUDC Davos instrument;
  missing 2026 observations stay missing. Use full-day observed maxima, and
  keep prescribed-albedo historical diagnostics distinct from production runs.
  Reproduce previous 08–16 UTC hourly results as an acquisition bridge check.
- Initial targets: >=90% within one displayed unit, >=80% exact category,
  <5% underprediction by >=2 categories. Denominator is usable paired site-days;
  report requested/unavailable counts separately. Report each threshold's miss
  denominator, category confusion, bias and 90th-percentile absolute error.
- Use paired seasonal moving-block bootstrap over chronological dates, block
  length three sampled dates (~15 days), 2000 replicates, seed 20260906.
  Keep all sites and both forecast methods together within each resampled date.
  Report percentile 95% intervals and block-length 1/6 sensitivity. Sparse
  strata (<20 dates) and unobserved categories are insufficient evidence;
  single-site intervals do not establish spatial generalization.
- Point estimates meeting a target alone are not qualification. A supported
  pass requires the relevant one-sided bound of the two-sided 95% interval to
  meet it and adequate coverage of the intended use. Separate each lead day
  and ICON configuration. Large winter samples must not conceal summer errors.
- All existing dates have previously been inspected: this phase is retrospective
  baseline/attribution, with no empirical fitting. Before tuning a candidate,
  reserve new dates or independent sites and record their identities without
  viewing outcomes. Do not relabel old dates as an untouched holdout.

Sources: [MeteoSwiss UV-index description](https://www.meteoswiss.admin.ch/weather/weather-and-climate-from-a-to-z/uv-index.html)
and [goal/acceptance rationale](PRODUCT_READINESS_GOAL.md). The exact numerical
aggregation and acceptance rules above are project decisions, not attributed to
those external documents.
