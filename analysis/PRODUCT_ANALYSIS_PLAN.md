# Daily baseline and attribution plan

Fixed before new daily scores, 6 September 2026. Implements
[product contract v1](PRODUCT_CONTRACT_V1.md); the prior hourly results remain
unchanged and are not an untouched evaluation set.

All 150 initializations remain in the ledger. Compare separately for each lead
day: reconstructed native-SW UV at prescribed albedo 0.05; gray-cloud baseline
at the same albedo; each method with quality-4 nearby DAV measured SW substituted
for model SW; and native-SW sensitivities at UV albedo 0.15 and 0.80. No fit or
selection of the best surface scenario by observations. Measured-SW substitution
is an attribution experiment, not an operationally available forecast input.

Interpolate CAMS ozone/AOD to the hourly midpoint, retain native broadband
albedo, and adjust native pressure to the WOUDC-reported 1590 m using the existing
8434 m scale height. Infer cloud using 12 solar samples per hour; reconstruct
five-minute solar samples and the 30-minute maxima specified in the contract.
Gray-cloud scaling is observed/model SW divided by the modeled hourly clear SW;
it is not fitted. At night set zero only when solar geometry establishes night;
do not divide a negligible clear-SW value into a large unexplained SW flux.

Require observed UV coverage in all daylight-containing UTC hours. Cadence rules
are those in the frozen UV study. Reject nonfinite/negative irradiance or excessive
gaps intersecting these hours. Use actual raw-sample integration of every
five-minute-start 30-minute window; nighttime missing samples can contribute zero
only outside daylight-containing hours. Record 30-minute and hourly maxima from
the same valid date and quantify their difference and category consequences.

Use the nearby DAV snow and sunshine observations at the hour containing the
observed peak midpoint as descriptive regime labels. Retain missing/QC failure as
unknown. DAV and WOUDC positions are not identical; report their separation.
Assess mean native-versus-observed SW error over the daylight-containing hours.

Scores include the frozen display/category metrics, raw-threshold miss rates,
requested and paired counts, and per-date predictions. Bootstrap whole dates,
stratified by season, with circular moving blocks of three sampled dates,
2000 replicates and seed 20260906; report block sizes one and six as sensitivity.
Keep paired methods on common dates for their MAE comparison. Separate scientific
point estimates from evidence sufficient to pass a target. No spatial confidence
claim is possible from the one fixed historical UV instrument.

Saved new inputs receive a manifest before scoring. The source contract, analysis
plan, radiation table and old WOUDC manifest receive SHA-256 identities. Fail on
changed inputs; do not rewrite expected hashes to make replay pass.
