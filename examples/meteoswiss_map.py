"""Export the MeteoSwiss map locations from a saved UV grid and print their values."""

import argparse
import hashlib
import json
from pathlib import Path

import xarray as xr

from icon_uv.daily import export_daily, write_json_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, required=True, help="Saved hourly UV NetCDF")
    parser.add_argument("--issued-at", required=True, help="Timezone-aware issuance, e.g. YYYY-MM-DDT06:00:00Z")
    parser.add_argument("--output", type=Path, default=Path("work/meteoswiss-map.json"))
    args = parser.parse_args()

    catalog_path = Path(__file__).with_name("meteoswiss_map_locations.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    with args.grid.open("rb") as stream:
        input_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    with xr.open_dataset(args.grid) as grid:
        payload = export_daily(
            grid.load(), catalog, args.issued_at, input_sha256=input_sha256, days='all',
        )
    write_json_atomic(payload, args.output)

    for day in range(len(payload['valid_dates'])):
        rows = [row for row in payload["entries"] if row["day"] == day]
        print(f"\n{rows[0]['valid_date']} (Europe/Zurich)")
        print(f"{'Location':<29} {'UVI':>4}  {'Category':<10}  Status")
        for row in rows:
            location = row["location"]
            label = location["label"]
            if location["kind"] == "region_altitude":
                label += f" {location['altitude_m']} m"
            value = "—" if row["display_uvi"] is None else str(row["display_uvi"])
            category = row["category"] or "—"
            reasons = f" ({', '.join(row['reasons'])})" if row["reasons"] else ""
            print(f"{label:<29} {value:>4}  {category:<10}  {row['status']}{reasons}")
    print(f"\nJSON: {args.output}")


if __name__ == "__main__":
    main()
