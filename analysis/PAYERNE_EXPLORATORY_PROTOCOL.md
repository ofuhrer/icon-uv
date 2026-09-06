# Payerne reserved-data adapter: provisional observational test

Frozen 6 September 2026 before reading any Payerne UV magnitudes or scoring any
of the 84 reserved initializations. This extends, and does not overwrite, the
earlier source assessment. It does not claim final observation qualification.

New evidence resolves two previous uncertainties sufficiently for an explicit
provisional test. July 2025 contains 44,639 consecutive one-minute timestamps
(00:00 July 1 to 23:58 July 31); the final missing minute is not evidence of a
two-minute cadence. GCOS-174 Table A1 identifies LR0500 fields as mean/std/min/max,
and the BSRN archive specifies UTC. The monthly DOI identifies the UV-b global
instrument as Solar Light 501A. The manufacturer's 501 documentation identifies
the UV-B biometer as erythemally weighted, while MeteoSwiss's CHARM/GAW description
identifies the measurements at Payerne as erythemal UV. Use the archive's already
converted W/m² multiplied by 40, never a voltage or MED conversion.

Use the fixed 84-date reservation, both forecast days, and the 14 monthly DOI
records already inventoried (August 2024–September 2025). Record current source
hashes and metadata. The six January–June 2025 records omit the global instrument
identity; keep these in the coverage roster but exclude them from the principal
Payerne subset. Do not fill that history by assuming instrument continuity.
December's explicit 12 December change is preserved as a separate instrument era.
Include the named-instrument months as provisional evidence; no per-minute
calibration/QC certificate is available, and this is stated in all conclusions.

Location: BSRN 46.8123 N, 6.9422 E, ground 491 m, sensor 2 m above ground;
evaluate UV at 493 m. Native cell 185266 is independently established in the
earlier metadata-only investigation. No change to model/table parameters.

The archive does not explicitly resolve minute start/centre/end labelling.
Prescribe centred one-minute means as the central adapter and evaluate both
start- and end-labelled alternatives (±30 seconds) as temporal uncertainty,
not as competing candidates from which a favourable answer is chosen. Integrate
piecewise constant means into half-hour windows; require full temporal support,
no gaps, finite nonnegative UV, and min <= mean <= max when all three are given
(allow 0.00001 W/m² for decimal rounding). Reject negative standard deviation.
Report missing/bad QC explicitly. No threshold based on disagreement with ICON.
Retain daily five-minute rolling 30-minute peaks plus common half-hour-grid peaks.
Report the full range across the three time conventions beside central scores.
Minute phase uncertainty must remain visible until confirmed by the data owner.

Retrieve the matching BSRN shortwave files for true colocated attribution; require
complete hourly intervals and nonnegative means, and apply documented broad
physical checks independently of ICON. Nearby DWH PAY shortwave remains a
separate labelled diagnostic if BSRN shortwave is unavailable or fails checks.
Missing SW hours exclude their paired UV windows; a daily score additionally
requires every daylight SW hour. Fully astronomical night is zero solar flux.
Computational zero placeholders for missing daytime SW are never scored.

This is authorized internal model validation using published archive data with
source attribution. It does not release raw BSRN data or imply scientific outreach.

Sources:
- Vuilleumier, L., Payerne monthly UV datasets, 2024-08–2025-09: individual DOIs in
  `work/independent-payerne-20260906/inventory.json`.
- https://bsrn.awi.de/data/station-to-archive-file-format/
- https://bsrn.awi.de/fileadmin/user_upload/bsrn.awi.de/Publications/gcos-174.pdf
- https://bsrn.awi.de/data/conditions-of-data-release/
- https://www.solarlight.com/product/uvb-biometer-model-501-radiometer
- https://www.meteoswiss.admin.ch/dam/jcr%3Aa296aaff-5472-44da-b7ef-e1db01d8ab11/theswisscontributiontothewmoglobalatmospherewatchprogramme.pdf
