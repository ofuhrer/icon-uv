# Payerne source assessment

6 September 2026. The 84 initialization dates reserved in
[the independent-site plan](INDEPENDENT_SITE_PLAN.md) remain unscored. This is a
metadata assessment, not an additional 84-case UV validation result.

The reproducible `analysis.inventory_payerne` inventory found 14 monthly UV
publications and 14 matching basic/other-radiation publications, August 2024 to
September 2025. The original search responses, complete parameter/instrument
metadata, revision timestamps, DOI identities and their hashes are retained in
`work/independent-payerne-20260906`. Only the header of the downloaded July UV
file was inspected. Its outcome values and model errors have not been viewed.

The published global UV field uses W/m². Metadata identify Solar Light 501A
SN 3551 / WRMC 21052 in August–November 2024, with a change to WRMC 21099 on
12 December 2024. July–September 2025 identify SN 26795 / WRMC 21099. The
January–June 2025 search metadata omit the instrument on the global UV column;
the December change alone does not establish the calibration history of those
six months. Full XML snapshots retain all other instrument changes and comments.
[November UV publication](https://doi.pangaea.de/10.1594/PANGAEA.984947),
[July UV publication](https://doi.pangaea.de/10.1594/PANGAEA.992977).

Historical MeteoSwiss/BSRN reports describe Payerne's Solar Light measurements
as erythemally weighted and discuss calibration and inter-instrument
uncertainty. This supports the intended quantity, but those reports are not
calibration certificates for the 2024–2025 serials. The source assessment therefore
does not yet approve an unconditional W/m² × 40 adapter for qualified scoring.
[BSRN calibration report](https://www.wcrp-climate.org/images/reports/2006/BSRN-9-2006.pdf),
[MeteoSwiss study](https://www.meteoswiss.admin.ch/dam/jcr%3A7ef169ae-ff2d-4adb-8fcc-ff1f5b16cb13/projekt-walker.pdf).

BSRN specifies UTC and logical-record statistics including means, minima,
maxima and standard deviations. The inspected material does not establish the
exact averaging interval and start/centre/end timestamp convention of these
recent UV records. The July UV metadata end at 23:58, whereas the corresponding
basic radiation series can end at 23:59; their supports must not be assumed
identical from timestamp names alone. Archive-wide detailed QC flags are not
provided. Enhanced publication curation is distinct from per-sample scientific
quality qualification. Station-level QC procedures documented internally provide
useful context, but their monthly decisions were not accessible from Balfrin.
[BSRN retrieval and QC scope](https://bsrn.awi.de/data/data-retrieval-via-pangaea/),
[BSRN file format](https://bsrn.awi.de/data/station-to-archive-file-format/),
[September shortwave publication](https://doi.pangaea.de/10.1594/PANGAEA.992989).

The source publications use the BSRN-1.0 license; preserve their individual
citations with any eventual scored data release. The archive errata page was
checked for a Payerne-specific entry; no matching entry was found. This is not
proof that every record is error-free.

Native input reuse is feasible: independently recomputing distances from the
checksummed 81,979-cell source grid gives cell **185266**, 0.847 km from the
published BSRN location 46.8123 N, 6.9422 E. It is exactly the already extracted
PAY column 93. Preserve the BSRN surface altitude 491 m and sensor height 2 m,
rather than silently replacing them with the SMN altitude. Saved historical
Davos CAMS fields do not cover Payerne, so they cannot be reused there.

The next scientific step is to resolve the recent calibration/weighting and
temporal-support metadata, obtain monthly QC decisions or explicitly qualify
an independent QC procedure, and freeze the adapter before looking at scores.
Then acquire Payerne CAMS fields and run the unchanged candidate and paired
shortwave attribution over all 84 reserved dates. Missing/QC-failed days remain
in the exclusion ledger. Do not fit the candidate to those outcomes and call
the same set independent. No outreach or public data release has been made.
