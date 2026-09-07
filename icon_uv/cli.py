"""Single small CLI; all core operations are also ordinary Python functions."""
import argparse
import hashlib
import json
from pathlib import Path

import xarray as xr

from .data import BBOX, fetch_cams, fetch_icon, load_cams, write_netcdf
from .products import POI, compute_grid, compute_pois
from .radiation import DEFAULT_TABLE, RadiationTable


def main():
    p = argparse.ArgumentParser(description="Compute UV Index fields and daily map data from ICON and CAMS")
    commands = p.add_subparsers(dest="command", required=True)
    icon = commands.add_parser("fetch-icon", help="Fetch a native-grid ICON-CH2 control subset")
    icon.add_argument("--reference", required=True)
    icon.add_argument("--first-lead", type=int, required=True)
    icon.add_argument("--last-lead", type=int, required=True)
    icon.add_argument("--bbox", type=float, nargs=4, default=BBOX, metavar=("W", "S", "E", "N"))
    icon.add_argument("--output", type=Path, required=True)
    cams = commands.add_parser("fetch-cams", help="Fetch CAMS ozone/AOD using your configured ADS account")
    cams.add_argument("--reference", required=True)
    cams.add_argument("--first-lead", type=int, required=True)
    cams.add_argument("--last-lead", type=int, required=True)
    cams.add_argument("--bbox", type=float, nargs=4, default=BBOX)
    cams.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Compute hourly grid fields from saved ICON and CAMS data")
    run.add_argument("--icon", type=Path, required=True)
    run.add_argument("--cams", type=Path, required=True)
    run.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    run.add_argument("--chunk-size", type=int, default=2048)
    run.add_argument("--output", type=Path, required=True)
    poi = commands.add_parser("poi", help="Recompute POIs with caller-provided local geometry JSON")
    poi.add_argument("--grid", type=Path, required=True)
    poi.add_argument("--locations", type=Path, required=True)
    poi.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    poi.add_argument("--output", type=Path, required=True)
    daily = commands.add_parser("daily", help="Export daily map data from a saved UV grid")
    daily.add_argument("--grid", type=Path, required=True)
    daily.add_argument("--catalog", type=Path, required=True)
    daily.add_argument("--days", choices=("2", "all"), default="2", help="Two days (default), or every supplied forecast day")
    daily.add_argument("--issued-at", required=True, help="Timezone-aware issuance timestamp; also fixes replay dates")
    daily.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    daily.add_argument("--output", type=Path, required=True)
    build = commands.add_parser("build-table", help="Developer only: rebuild LUT with libRadtran")
    build.add_argument("--lib", type=Path, required=True)
    build.add_argument("--cache", type=Path, required=True)
    build.add_argument("--output", type=Path, default=DEFAULT_TABLE)
    build.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    if args.command == "fetch-icon":
        ds = fetch_icon(args.reference, args.first_lead, args.last_lead, args.bbox)
        write_netcdf(ds, args.output)
    elif args.command == "fetch-cams":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fetch_cams(args.reference, range(args.first_lead, args.last_lead+1, 3), args.output, args.bbox)
    elif args.command == "run":
        with xr.open_dataset(args.icon) as ds:
            result = compute_grid(ds.load(), load_cams(args.cams), RadiationTable(args.table), chunk_size=args.chunk_size, progress=True)
        write_netcdf(result, args.output)
    elif args.command == "poi":
        locations = [POI(**item) for item in json.loads(args.locations.read_text())]
        with xr.open_dataset(args.grid) as ds:
            result = compute_pois(ds.load(), locations, RadiationTable(args.table))
        write_netcdf(result, args.output)
    elif args.command == "build-table":
        from .build_table import build as make_table
        make_table(args.lib, args.output, args.cache, workers=args.workers)
    elif args.command == "daily":
        from .daily import export_daily, write_json_atomic
        with xr.open_dataset(args.grid) as ds:
            payload = export_daily(ds.load(), json.loads(args.catalog.read_text()), args.issued_at,
                                   days='all' if args.days == 'all' else 2,
                                   table=RadiationTable(args.table),
                                   input_sha256=hashlib.sha256(args.grid.read_bytes()).hexdigest())
        write_json_atomic(payload, args.output)


if __name__ == "__main__":
    main()
