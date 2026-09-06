"""Bounded DWH availability probes; report counts, never observation magnitudes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import subprocess
import time


def probe(spec, output):
    name, stage, date, explicit_url = spec
    path = output/f'{name}.csv'
    command = ['/oprusers/osm/opr.inn/bin/jretrievedwh', '--stage', stage, '--timeout', '45',
               '-s', 'surface', '-i', 'nat_abbr,PAY,DAV,JUN,OTL,WFJ',
               '-n', 'ouib02t0,ouib02tq,ouib0bt0,ouib0btq,gor000t0,gor000tq,gre000h0',
               '-t', date+'1100,'+date+'1200', '-r', '1', '--use-limitation', '50',
               '--format', 'csv', '-j', 'nat_abbr,lat,lon,elev', '-o', str(path)]
    if explicit_url:
        command += ['--url', explicit_url]
    start = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=65)
        body = path.read_text() if path.exists() else ''
        counts = {}
        if body.startswith('station;termin;'):
            reader = csv.reader(io.StringIO(body), delimiter=';'); header = next(reader)
            for row in reader:
                if len(row) != len(header):
                    continue
                station = row[header.index('nat_abbr')]
                count = counts.setdefault(station, {})
                for field in ('ouib02t0','ouib02tq','ouib0bt0','ouib0btq','gor000t0','gor000tq','gre000h0'):
                    count[field] = count.get(field, 0) + int(row[header.index(field)] not in ('','NA','NaN'))
        record = dict(name=name, command=command, exit_code=result.returncode,
                      valid_header=body.startswith('station;termin;'), nonmissing_counts=counts,
                      sha256=hashlib.sha256(body.encode()).hexdigest(), seconds=time.monotonic()-start)
        # Client stderr is kept locally for diagnostics; never capture auth configuration.
        (output/f'{name}.stderr').write_text(result.stderr)
    except subprocess.TimeoutExpired:
        record = dict(name=name, command=command, status='timeout', seconds=time.monotonic()-start)
    (output/f'{name}.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record), flush=True)
    return record


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    specs = [(f'{stage}_{date}', stage, date, None)
             for stage in ('prod','devt','depl')
             for date in ('20241203','20250703','20260803')]
    specs.append(('explicit_devt_20241203','devt','20241203',
                  'https://servicedevt.meteoswiss.ch/jretrieve/api/v1'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(lambda s: probe(s, output), specs))
    (output/'availability.json').write_text(json.dumps(records, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
