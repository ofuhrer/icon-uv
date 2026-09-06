"""Extract a fixed ICON archive campaign on a CSCS CPU node.

Only selected native-cell values and GRIB identities/hashes leave the archive.
No production radiation algorithm is changed. Run with --campaign and --output.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

# GRIB2 discipline/category/number, surface type 1. DWD ICON database table.
FIELDS = {(0, 4, 198): 'direct', (0, 4, 199): 'diffuse',
          (0, 3, 0): 'pressure', (0, 19, 1): 'albedo', (0, 1, 11): 'snow_depth'}


def extract_file(path, reference, lead, ids, grid_uuid, height=False):
    import eccodes as ec
    fields, records = {}, []
    wanted = {(0, 3, 6): 'height'} if height else FIELDS
    with path.open('rb') as stream:
        while (gid := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                key = tuple(ec.codes_get_long(gid, k) for k in
                            ('discipline', 'parameterCategory', 'parameterNumber'))
                if key not in wanted or ec.codes_get_long(gid, 'typeOfFirstFixedSurface') != 1:
                    continue
                name = wanted[key]
                if name in fields:
                    raise ValueError(f'Duplicate {name} in {path.name}')
                message = ec.codes_get_message(gid)
                raw_time = {k: ec.codes_get(gid, k) for k in ('indicatorOfUnitOfTimeRange', 'forecastTime')}
                ec.codes_set(gid, 'stepUnits', 1)  # accessor normalization: minutes -> hours
                meta = {k: ec.codes_get(gid, k) for k in
                        ('dataDate', 'dataTime', 'endStep', 'startStep', 'stepUnits',
                         'stepType', 'uuidOfHGrid', 'perturbationNumber', 'numberOfDataPoints',
                         'units', 'packingError', 'centre', 'localTablesVersion')}
                for time_key in ('endStep', 'startStep'):
                    meta[time_key] = ec.codes_get_double(gid, time_key)
                for key_name in ('dataDate','dataTime','stepUnits','perturbationNumber','numberOfDataPoints'):
                    meta[key_name] = ec.codes_get_long(gid, key_name)
                meta['raw_time'] = raw_time
                expected = (int(reference.strftime('%Y%m%d')), 0, lead, 1, grid_uuid, 0)
                actual = tuple(meta[k] for k in ('dataDate', 'dataTime', 'endStep',
                                                'stepUnits', 'uuidOfHGrid', 'perturbationNumber'))
                if actual != expected or max(ids) >= meta['numberOfDataPoints']:
                    raise ValueError(f'ICON identity mismatch: {path.name} {name} {actual}')
                if name in ('direct', 'diffuse'):
                    if meta['stepType'] != 'avg' or meta['startStep'] != 0:
                        raise ValueError('Expected radiation mean since initialization')
                    # Generic ecCodes does not resolve lssw local table 1. Only
                    # these exact documented local parameter IDs are accepted.
                    if meta['centre'] != 'lssw' or meta['localTablesVersion'] != 1:
                        raise ValueError('Unqualified local radiation parameter table')
                    if meta['units'] not in ('unknown', 'W m**-2'):
                        raise ValueError('Unexpected radiation units')
                else:
                    if meta['stepType'] != 'instant':
                        raise ValueError(f'Expected instantaneous {name}')
                    unit = {'pressure': 'Pa', 'albedo': '%', 'snow_depth': 'm', 'height': 'm'}[name]
                    if meta['units'] != unit:
                        raise ValueError(f'Unexpected units: {name} {meta["units"]}')
                values = np.asarray(ec.codes_get_elements(gid, 'values', ids), dtype=float)
                if not np.isfinite(values).all() or (np.abs(values) > 1e10).any():
                    raise ValueError(f'Missing values in {name}')
                fields[name] = values
                records.append(dict(field=name, parameter=list(key), source=str(path),
                                    sha256=hashlib.sha256(message).hexdigest(), **meta))
            finally:
                ec.codes_release(gid)
            if height and 'height' in fields:
                break
    missing = set(wanted.values()) - set(fields)
    if missing - {'snow_depth'}:
        raise ValueError(f'Missing required fields in {path}: {missing}')
    if 'snow_depth' in missing:
        fields['snow_depth'] = np.full(len(ids), np.nan)
    return fields, records


def extract_case(case, cfg, output):
    date = datetime.fromisoformat(case['reference'].replace('Z', '+00:00'))
    stem = date.strftime('%Y%m%d_00')
    print(f'Extracting {stem}', flush=True)
    target = output / (stem + '.npz')
    manifest = output / (stem + '.json')
    if target.exists() and manifest.exists():
        saved = json.loads(manifest.read_text())
        if (saved['campaign_sha256'] != cfg['campaign_sha256'] or
                saved['output_sha256'] != hashlib.sha256(target.read_bytes()).hexdigest()):
            raise ValueError(f'Cached input changed: {stem}')
        return {'date': case['date'], 'status': 'reused'}
    base = Path(cfg['archive']) / date.strftime('FCST%y')
    candidates = sorted(base.glob(date.strftime('%y%m%d00') + '_*'))
    if len(candidates) != 1:
        raise ValueError(f'Expected one archive configuration for {stem}, found {len(candidates)}')
    directory = candidates[0] / 'grib'
    ids = [s['cell'] for s in cfg['stations'] + cfg.get('uv_stations', [])]
    height, records = extract_file(directory / 'i2eff00000000_000', date, 0, ids,
                                   cfg['grid_uuid'], height=True)
    boundary = {name: [] for name in FIELDS.values()}
    for lead in cfg['boundary_leads']:
        path = directory / f'i2eff{lead//24:02d}{lead%24:02d}0000_000'
        values, metadata = extract_file(path, date, lead, ids, cfg['grid_uuid'])
        for name in boundary:
            boundary[name].append(values[name])
        records.extend(metadata)
    arrays = {name: np.asarray(values) for name, values in boundary.items()}
    arrays.update(height=height['height'], leads=cfg['boundary_leads'], cell=ids)
    temporary = target.with_suffix('.tmp.npz')
    np.savez_compressed(temporary, **arrays)
    temporary.replace(target)
    document = dict(reference=case['reference'], configuration=candidates[0].name.split('_')[1],
                    grid_uuid=cfg['grid_uuid'], member=0, records=records,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                    campaign_sha256=cfg['campaign_sha256'],
                    output_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(document, indent=2))
    return {'date': case['date'], 'status': 'extracted', 'configuration': document['configuration']}


def retrieve_observations(case, cfg, output):
    date = datetime.fromisoformat(case['reference'].replace('Z', '+00:00'))
    paths = []
    for day in (0, 1):
        start = date + timedelta(days=day, hours=9)
        end = date + timedelta(days=day, hours=16)
        path = output / f"{date:%Y%m%d}_day{day}.csv"
        if not path.exists():
            temporary = path.with_suffix('.tmp.csv')
            command = ['/oprusers/osm/opr.inn/bin/jretrievedwh', '--stage', 'prod',
                       '--timeout', '60', '-s', 'surface', '-i',
                       'nat_abbr,' + ','.join(s['station'] for s in cfg['stations']),
                       '-n', 'gre000h0,sre000h0,prestah0,htoauths,rre150h0', '-t',
                       f'{start:%Y%m%d%H%M},{end:%Y%m%d%H%M}', '-r', '1',
                       '--format', 'csv', '-j', 'nat_abbr,lat,lon,elev', '-o', str(temporary)]
            subprocess.run(command, check=True, timeout=90, capture_output=True)
            data = temporary.read_text()
            if '# ERROR' in data or not data.startswith('station;termin;') or len(data.splitlines()) < 2:
                raise ValueError(f'Observation request failed or empty: {case["date"]} day {day}')
            temporary.replace(path)
        paths.append(dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return {'date': case['date'], 'status': 'retrieved', 'inputs': paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['icon', 'observations'], required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    args = parser.parse_args()
    cfg = json.loads(args.campaign.read_text())
    cfg['campaign_sha256'] = hashlib.sha256(args.campaign.read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = cfg['cases'][args.shard::args.shards][:args.limit]
    function = extract_case if args.mode == 'icon' else retrieve_observations
    def run(case):
        try:
            return function(case, cfg, args.output)
        except Exception as error:
            return dict(date=case['date'], status='failed', error=f'{type(error).__name__}: {error}')
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(run, cases):
            results.append(result)
            print(json.dumps(result), flush=True)
    (args.output / f'acquisition_{args.shard}.json').write_text(json.dumps(results, indent=2))
    if any(r['status'] == 'failed' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
