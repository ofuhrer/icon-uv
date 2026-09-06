# Goal: reliable UV data for daily public information products

Defined 6 September 2026, following the user's map example and preference for
practical reliability over very high absolute precision.

## Objective and scope

Develop and evaluate a reproducible data pipeline that can supply today/tomorrow
UV map products for Swiss towns and mountain regions at 1000, 2000 and 3000 m.
Deliver daily peak estimates, display integers, exposure categories, validity
dates, locations/elevations and explicit quality/freshness information. Optimize
for useful displayed values, reliable category decisions and robust delivery.
Do not spend effort improving decimal precision unless it materially improves
these outcomes. The deliverable is the data and evidence needed by a product
renderer; building or publishing the illustrated website is outside this goal.

The attachment is a product example, not a specification of its undocumented
algorithm. Do not infer exact coordinates, region aggregation, rounding or peak
averaging rules from the image. MeteoSwiss describes its UV forecast as a daily
maximum that includes cloud effects. The current hourly-mean validation does not
establish daily-maximum accuracy.

## Work sequence

1. **Freeze the product contract before scoring it.** Define all-sky daily peak,
   its averaging interval, full-day coverage requirements, Europe/Zurich valid
   dates and daylight-saving handling, rounding, and category boundaries.
   Establish whether existing hourly inputs can support the intended peak
   definition, quantify temporal smoothing, and label any approximation.
   Keep raw values and displayed values distinct; retain values above 11, zero
   and missing values correctly. Define stable town/region identifiers and
   representative locations/elevations without inventing official geography.
   Regional altitude estimates need an explicit spatial and cloud/snow treatment,
   not just a universal percentage adjustment with altitude.

2. **Establish a product-level baseline and attribute errors.** Reuse the frozen
   150-case ICON campaign and available UV records, retaining exclusions and
   counting distinct dates/sites. Evaluate daily displayed values and category
   confusion separately for today and tomorrow. Compare the existing UV method
   and gray-cloud baseline on identical cases. Where observational support is
   adequate, substitute measured SW while keeping other drivers fixed, then
   compare supported surface assumptions. Record separation between nearby SW
   and UV instruments as a limitation of attribution. Examine snow, sunshine,
   seasons, elevations and ICON configurations separately.

3. **Resolve the largest product-relevant limitations.** Prioritize snow/albedo,
   cloud response, regional elevation representativeness, seasonal profiles and
   peak sampling according to their effect on displayed values/categories.
   Use targeted direct radiative-transfer checks and paired comparisons. Retain
   the simpler method unless added complexity produces a useful improvement.
   Keep candidate tables and inputs separate from the completed frozen studies.
   Reserve dates or sites for evaluation before any fitting; do not tune to the
   reported verification set and then claim independent validation.

4. **Strengthen observational and production coverage.** Seek independently
   quality-controlled UV at multiple Swiss sites/elevations and snow conditions.
   Retrieve authentic production snow inputs where possible; explicitly label
   cases that still require assumptions. Assess current ICON configuration
   evidence separately. Use available complete recent cycles for end-to-end
   demonstrations. A single-site or sparse extreme-category sample cannot
   qualify unobserved locations or conditions.

5. **Implement and exercise the product data interface.** Provide a documented,
   versioned machine-readable export and reproducible command for town and
   altitude products for both days. Include source cycles, UTC timestamps,
   local valid date, units, spatial support, peak definition and quality state.
   Test missing/late/corrupt drivers, partial daylight coverage, mismatched
   cycles, unsupported elevations, output atomicity and deterministic replay.
   Stale or incomplete data must never silently become a fresh normal forecast;
   any fallback must have an explicit identity, age limit and validation scope.
   Supply a sample payload covering the kinds of entries shown in the image.

6. **Deliver a readiness decision and remaining gaps.** Produce a reproducible
   scorecard, documented interface, tests and example outputs. Distinguish
   supported uses, conditional uses and unsupported uses. Report insufficient
   evidence explicitly; do not force a favorable conclusion to finish the goal.

## Working acceptance targets

These are initial engineering targets for this project, not official MeteoSwiss
or health-agency acceptance standards. Freeze exact metric definitions and the
evaluation split before computing the new product scorecard. Changes to targets
must be recorded with reasons, not made silently after observing results.

- At least 90% of evaluated site-days within one displayed UVI unit and at
  least 80% in the same displayed exposure category as observations.
- Fewer than 5% of evaluated site-days underestimated by two or more categories.
  Also report misses across each important category boundary, especially
  predicted low versus observed moderate-or-higher, and predicted below-high
  versus observed very-high/extreme. Pooled accuracy must not hide these misses.
- Report denominators, coverage, confusion matrices, bias, upper error quantiles
  and uncertainty that preserves dependence within dates and sites. Assess
  seasons, sites, snow regimes and configurations; insufficient subgroup
  evidence is not a pass. Small point-estimate differences do not establish
  superiority over the baseline.
- Every requested output entry is either valid under the documented contract
  or explicitly unavailable/degraded. No missing-to-zero conversion, silent
  partial-day maximum, unlabeled stale cycle, inconsistent category/number or
  accepted corrupt input in the defined reliability tests.
- Complete a frozen end-to-end replay and sample today/tomorrow export for
  towns and mountain elevation entries. Measure runtime and resource use;
  establish an operational latency budget from the intended publication cycle.
  Offline tests do not establish a live service availability percentage.

Meeting this goal means delivering the implementation and an honest readiness
assessment against these targets. It does not mean automatic public deployment
or declaring every target met when observations are insufficient. No outreach,
publication or recurring collection job is implied by this goal definition.

## Evidence and sources

- [Existing multi-year findings](MULTIYEAR_FINDINGS.md): 150 native SW dates;
  67 Davos UV diagnostic dates under prescribed albedo; latest configuration
  represented by only four dates.
- [MeteoSwiss UV-index description](https://www.meteoswiss.admin.ch/weather/weather-and-climate-from-a-to-z/uv-index.html):
  cloud-aware forecast of maximum intensity. Exact averaging/rounding and
  regional implementation still require a documented product contract.
- [WHO UV-index information](https://www.who.int/news-room/questions-and-answers/item/radiation-the-ultraviolet-%28uv%29-index):
  authoritative context for public UV-index communication.
- User-supplied map: town values, regional 1000/2000/3000 m values, today/tomorrow
  navigation, and categories 1–2, 3–5, 6–7, 8–10 and 11+.
