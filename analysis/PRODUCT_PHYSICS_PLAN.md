# Product-relevant physical stress checks

6 September 2026. Freeze this protocol before calculating the new results.
This is a solver sensitivity experiment, not observational validation or a fit.
Preserve the production table and all previous campaigns.

Use libRadtran 2.0.6, the existing eight-stream plane-parallel DISORT settings,
0.5 nm erythemal integration and 1 AU fluxes. Cross 25/65 degree solar zenith,
500/1500/3000 m pressure-equivalent elevation, surface albedo 0.05/0.8 and
liquid-cloud optical depth 0/10: 24 states. Fix ozone at 300 DU and AOD550 at
0.1. Evaluate each state with the midlatitude-summer profile/20 mm water used
by the table, midlatitude-winter/20 mm, and midlatitude-winter/5 mm. The last
comparison separates profile shape from water-column effects. The combinations
are controlled stress states, not a frequency-weighted Swiss climatology.

For every direct calculation, infer the effective cloud from its broadband SW
using the unchanged runtime table, then evaluate UV. Report raw UVI error,
display integer/category changes and fitted cloud/extension flags. Compare the
same states between profiles to distinguish interpolation error from structural
sensitivity. Verify one summer result against the existing reference solver;
retain exact inputs, outputs and solver/data/source hashes. Nonfinite, negative
or energy-inconsistent direct results fail the calculation.

Report snow and elevation contrasts separately. These contrast physically
consistent native surfaces; they do not justify lifting a valley cloud to an
arbitrary altitude, nor treating uniform snow as regional effective albedo.
No adjustment will be fitted from these results. A reference-model comparison
cannot validate unresolved three-dimensional cloud enhancement or local terrain.
