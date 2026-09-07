"""Single small CLI; all core operations are also ordinary Python functions."""
import argparse
import json
import sys
from pathlib import Path

import xarray as xr

from .data import BBOX, fetch_cams, fetch_icon, load_cams, write_netcdf
from .products import compute_grid, compute_points
from .locations import load_locations
from .radiation import DEFAULT_TABLE, RadiationTable


def main():
    try:
        _main()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        if '--debug' in sys.argv:
            raise
        raise SystemExit(f'icon-uv: {exc}') from None


def _day_count(value):
    if value == 'all':
        return value
    try:
        count = int(value)
        if count < 1:
            raise ValueError
        return count
    except ValueError as exc:
        raise argparse.ArgumentTypeError("days must be a positive integer or 'all'") from exc


def _date_arguments(parser):
    dates = parser.add_mutually_exclusive_group()
    dates.add_argument('--days', type=_day_count, help="Positive number of local dates (default: 2), or all supplied daylight dates")
    dates.add_argument('--dates', nargs='+', metavar='YYYY-MM-DD', help='Explicit increasing local valid dates')


def _main():
    p = argparse.ArgumentParser(description="Compute UV Index fields and daily map data from ICON and CAMS")
    p.add_argument('--debug', action='store_true', help='Show full tracebacks for diagnostics')
    commands = p.add_subparsers(dest="command", required=True)
    icon = commands.add_parser("fetch-icon", help="Fetch a native-grid ICON-CH2 ensemble subset")
    members = icon.add_mutually_exclusive_group()
    members.add_argument('--ensemble', dest='ensemble', action='store_true', default=True,
                         help='All 21 members (default)')
    members.add_argument('--control', dest='ensemble', action='store_false', help='CTRL member 0 only')
    icon.add_argument('--minimum-member-fraction', type=float, default=.9, help='Minimum usable member/field fraction (default: 0.9; tolerate up to 10%% missing)')
    icon.add_argument("--reference", required=True)
    icon.add_argument("--first-lead", type=int, required=True)
    icon.add_argument("--last-lead", type=int, required=True)
    icon.add_argument("--bbox", type=float, nargs=4, default=BBOX, metavar=("W", "S", "E", "N"))
    icon.add_argument("--output", type=Path, required=True)
    cams = commands.add_parser("fetch-cams", help="Fetch CAMS ozone/AOD as NetCDF using your configured ADS account")
    cams.add_argument("--reference", required=True)
    cams.add_argument("--first-lead", type=int, required=True)
    cams.add_argument("--last-lead", type=int, required=True)
    cams.add_argument("--bbox", type=float, nargs=4, default=BBOX)
    cams.add_argument("--output", type=Path, required=True, help="Normalized NetCDF output (e.g. work/cams.nc)")
    run = commands.add_parser("run", help="Compute hourly grid fields from saved ICON and CAMS data")
    run.add_argument("--icon", type=Path, required=True, help="Normalized ICON NetCDF from fetch-icon")
    run.add_argument("--cams", type=Path, required=True, help="Normalized CAMS NetCDF from fetch-cams")
    run.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    run.add_argument("--chunk-size", type=int, default=2048)
    run.add_argument("--samples", type=int, choices=(1,2,4,6,12), default=4, help="Solar samples per hour (default: 4; use 12 for daily maps)")
    run.add_argument("--output", type=Path, required=True)
    poi = commands.add_parser("points", help="Hourly points from a location catalog")
    poi.add_argument("--grid", type=Path, required=True)
    poi.add_argument("--locations", dest="locations", type=Path, required=True)
    poi.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    poi.add_argument("--output", type=Path, required=True)
    daily = commands.add_parser("daily", help="Export daily map data from a saved UV grid")
    daily.add_argument("--grid", type=Path, required=True)
    daily.add_argument("--locations", dest="locations", type=Path, required=True)
    _date_arguments(daily)
    daily.add_argument('--terrain-screened', action='store_true', help='Use explicit horizons for a catalog of points')
    daily.add_argument("--issued-at", required=True, help="Timezone-aware issuance timestamp; also fixes replay dates")
    daily.add_argument('--ensemble-quantile', type=float, default=.5, help='Quantile of member daily products (default: 0.5, median)')
    daily.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    daily.add_argument("--output", type=Path, required=True)
    preflight = commands.add_parser('preflight', help='Check saved-grid state, native support, freshness and daylight coverage without computing UV')
    preflight.add_argument('--grid', type=Path, required=True)
    preflight.add_argument('--locations', dest='locations', type=Path, required=True)
    preflight.add_argument('--issued-at', required=True)
    preflight.add_argument('--table', type=Path, default=DEFAULT_TABLE)
    preflight.add_argument('--output', type=Path, help='Optional JSON report')
    _date_arguments(preflight)
    build = commands.add_parser("build-table", help="Developer only: rebuild LUT with libRadtran")
    build.add_argument("--lib", type=Path, required=True)
    build.add_argument("--cache", type=Path, required=True)
    build.add_argument("--output", type=Path, default=DEFAULT_TABLE)
    build.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    if args.command == "fetch-icon":
        ds = fetch_icon(args.reference, args.first_lead, args.last_lead, args.bbox, ensemble=args.ensemble, minimum_member_fraction=args.minimum_member_fraction)
        write_netcdf(ds, args.output)
    elif args.command == "fetch-cams":
        fetch_cams(args.reference, range(args.first_lead, args.last_lead+1, 3), args.output, args.bbox)
    elif args.command == "run":
        with xr.open_dataset(args.icon) as ds:
            result = compute_grid(ds.load(), load_cams(args.cams), RadiationTable(args.table), chunk_size=args.chunk_size, samples=args.samples, progress=True)
        write_netcdf(result, args.output)
    elif args.command == 'points':
        locations = load_locations(args.locations)
        with xr.open_dataset(args.grid) as ds:
            result = compute_points(ds, locations.points, RadiationTable(args.table))
        write_netcdf(result, args.output)
    elif args.command == "build-table":
        from .build_table import build as make_table
        make_table(args.lib, args.output, args.cache, workers=args.workers)
    elif args.command == "daily":
        from .daily import export_daily_file
        export_daily_file(args.grid, args.locations, args.issued_at, output=args.output,
                          ensemble_quantile=args.ensemble_quantile, days=args.days, dates=args.dates,
                          terrain_screened=args.terrain_screened, table=RadiationTable(args.table))
    elif args.command == 'preflight':
        from .preflight import preflight
        from .daily import write_json_atomic
        with xr.open_dataset(args.grid) as ds:
            report = preflight(ds, args.locations, args.issued_at, days=args.days,
                               dates=args.dates, table=RadiationTable(args.table))
        if args.output is not None:
            write_json_atomic(report, args.output)
        print(json.dumps(report, indent=2, allow_nan=False))
        if not report['ready']:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
