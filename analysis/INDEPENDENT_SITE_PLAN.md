# Reserved independent site: Payerne

6 September 2026. No Payerne UV outcome values or model errors have been viewed
for this product milestone. Reserve the existing roster's six dates per month
from August 2024 through September 2025 (84 initializations, plus next-day
windows) at the Payerne BSRN site for independent baseline/transfer assessment.
Retain every requested date, including missing records. Do not choose dates by
UV error or change the existing physics from these outcomes before reporting
the independent evaluation.

The current candidate is the fixed product contract, radiation table and native
UV method recorded in the product run identity. No empirical tuning has been
performed. Keep the gray baseline, measured-SW attribution and explicitly
prescribed surface sensitivities separate. Later candidate fitting requires
another untouched evaluation set or a split frozen before fitting.

The Payerne BSRN metadata give 46.812300 N, 6.942200 E, station elevation 491 m
and measurement height 2 m. Source instrument heights and changes must be
retained. Do not substitute the nearby SwissMetNet station metadata silently.

Before scoring:

1. Inventory monthly BSRN/PANGAEA UV and corresponding SW publications, saving
   DOI/citation, license, instrument identity/change dates, revision information,
   availability and input checksums. Missing data remains missing.
2. Verify what the `UV-b global` field measures: its erythemal weighting,
   calibration/conversion and units. The field name and plausible magnitude
   alone do not authorize multiplication by 40. Verify timestamp/averaging
   semantics and QC provenance separately from publication curation status.
3. Freeze the accepted adapter, inputs and any documented limitations before
   computing paired scores. Use the same daily-product definitions and uncertainty
   methods; do not pool sites into a geographical qualification without coverage.
4. Retrieve independent native state at the documented site and full daylight
   CAMS coverage; reuse existing native/CAMS values only after proving the same
   spatial support and source identities. Use colocated BSRN shortwave for
   attribution if its support and QC are verified.

Discovered primary records (metadata inspected; outcomes not yet inspected):

- Vuilleumier, Laurent (2026): Ultra-violet measurements from station Payerne
  (2025-07). MeteoSwiss, PANGAEA,
  [doi:10.1594/PANGAEA.992977](https://doi.pangaea.de/10.1594/PANGAEA.992977).
- Vuilleumier, Laurent (2025): Ultra-violet measurements from station Payerne
  (2024-11). MeteoSwiss, PANGAEA,
  [doi:10.1594/PANGAEA.984947](https://doi.pangaea.de/10.1594/PANGAEA.984947).
- Vuilleumier, Laurent (2026): Ultra-violet measurements from station Payerne
  (2025-09). MeteoSwiss, PANGAEA,
  [doi:10.1594/PANGAEA.992988](https://doi.pangaea.de/10.1594/PANGAEA.992988).

Other access checks: MeteoSwiss OGD SACRaM documentation still says the data are
not yet available. The documented internal `/proj/pay/CHARM/D_ged_qual_eval` and
`/prod/pay/SACRaM` paths are not available from the connected Balfrin login.
WOUDC lists Weissfluhjoch as a contributor station, but attempted broadband,
multiband and spectral archive paths returned 404; station listing alone is not
evidence of usable UV observations. These checks do not block the Payerne route
or further physical/interface work.
