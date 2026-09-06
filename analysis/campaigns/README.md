# Frozen experiment definitions

These are byte-identical copies of the experiment definitions used on
6 September 2026. They contain dates, native-cell/station mapping, grid identity,
boundary leads, archive location and protocol hashes, but no measured UV values,
downloaded forecasts or credentials. `checksums.json` records their identities.
The 84-date Payerne reservation is retained separately from the 150-date roster.

| Directory | Study |
|---|---|
| `scientific-multiyear-20260906` | 150 native ICON cases and SwissMetNet matching |
| `product-readiness-20260906` | Full-day product campaign and Payerne reservation |
| `swiss-uv-sites-20260906` | Five Swiss UV locations, three provisionally scored |

Analysis tools retain their original study paths to preserve replay compatibility.
For a new local archive, copy these definitions into the corresponding directory
under `work/`, preserving the relative paths. Do not overwrite existing files
without checking that their hashes match. Restore/retrieve the referenced source
grid and observations separately; the source-grid checksum alone is not the grid.
Native extraction needs authorized access to the named MeteoSwiss archive on
Balfrin. Public ICON retention is insufficient to recreate old cases unaided.

The acquisition scripts accept these `campaign.json` files as their `--campaign`
argument. Changed station mapping, sampling or protocol means a new campaign;
keep these historical definitions intact.
