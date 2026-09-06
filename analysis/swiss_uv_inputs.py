"""Acquire the fixed Swiss UV extension without displaying outcome values."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public(root):
    import requests
    cfg = json.loads((root / 'campaign.json').read_text())
    out = root / 'imed'; out.mkdir(exist_ok=True)

    def one(case):
        date = datetime.fromisoformat(case['date'])
        url = ('https://uv-data.i-med.ac.at/public/data/?product=uve&start='
               f'{date:%Y-%m-%d}&stop={date+timedelta(days=2):%Y-%m-%d}')
        path = out / f'{date:%Y%m%d}.json'; meta = path.with_suffix('.identity.json')
        if path.exists() and meta.exists():
            record = json.loads(meta.read_text())
            if record['url'] != url or record['sha256'] != sha(path):
                raise ValueError('Changed cached observation')
            return record
        r = requests.get(url, timeout=60); r.raise_for_status(); data = r.json()
        counts = {}
        for site in ('Davos', 'Weissfluhjoch'):
            v = data.get(site, {}).get('uve', {})
            if v and v.get('unit') != 'UV-Index':
                raise ValueError('Unexpected UV unit')
            if len(v.get('ts', [])) != len(v.get('measurement', [])):
                raise ValueError('Timestamp/value length mismatch')
            counts[site] = len(v.get('ts', []))
        tmp = path.with_suffix('.partial'); tmp.write_bytes(r.content); tmp.replace(path)
        record = dict(url=url, sha256=sha(path), bytes=len(r.content), counts=counts,
                      retrieved_at=datetime.now(timezone.utc).isoformat())
        meta.write_text(json.dumps(record, indent=2))
        return record

    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(one, cfg['cases']))
    (out / 'acquisition.json').write_text(json.dumps(records, indent=2))
    print('Acquired', len(records), 'fixed two-day UV windows', flush=True)


def cams(root, year):
    import cdsapi
    import eccodes as ec
    from icon_uv.data import cams_request, CAMS_DATASET
    cfg = json.loads((root / 'campaign.json').read_text())
    dates = [(datetime.fromisoformat(c['date']) - timedelta(days=1)).strftime('%Y-%m-%d')
             for c in cfg['cases'] if c['year'] == year]
    # Covers all discovered Swiss sites, even if some observations stay unavailable.
    request = cams_request(dates[0]+'T12:00:00Z', range(12,61,3), (6.8,46.0,10.0,47.0))
    request['date'] = dates
    out = root / 'cams'; out.mkdir(exist_ok=True)
    path = out / f'cams_{year}.grib'; meta = path.with_suffix('.json')
    if path.exists():
        saved = json.loads(meta.read_text())
        if saved['request'] != request or saved['sha256'] != sha(path):
            raise ValueError('Changed CAMS input')
    else:
        tmp = path.with_suffix('.partial')
        client = cdsapi.Client(url='https://ads.atmosphere.copernicus.eu/api',
                              retry_max=3, sleep_max=20, timeout=60)
        client.retrieve(CAMS_DATASET, request, str(tmp)); tmp.replace(path)
        meta.write_text(json.dumps(dict(dataset=CAMS_DATASET, request=request, sha256=sha(path),
                            retrieved_at=datetime.now(timezone.utc).isoformat()), indent=2))
    split = {}
    with path.open('rb') as stream:
        while (g := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(g, 'dataTime') != 1200:
                    raise ValueError('Wrong CAMS cycle')
                split.setdefault(ec.codes_get(g, 'dataDate'), bytearray()).extend(ec.codes_get_message(g))
            finally:
                ec.codes_release(g)
    if {str(d) for d in split} != {d.replace('-', '') for d in dates}:
        raise ValueError('Wrong CAMS dates')
    for date, data in split.items():
        target = out / f'cams_{date}_12.grib'
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Changed CAMS split')
        target.write_bytes(data)
    print('Acquired',len(split),'CAMS cycles',flush=True)


def payerne(root):
    import requests
    inventory = json.loads((ROOT/'work/independent-payerne-20260906/inventory.json').read_text())
    out=root/'payerne';out.mkdir(exist_ok=True)
    def one(record):
        url=record['doi'].replace('doi.org/','doi.pangaea.de/')+'?format=textfile'
        path=out/(record['start'][:7].replace('-','')+'_'+record['kind']+'.tab')
        meta=path.with_suffix('.json')
        if path.exists() and meta.exists():
            old=json.loads(meta.read_text())
            if old['sha256']!=sha(path) or old['url']!=url:raise ValueError('Changed Payerne input')
            return old
        r=requests.get(url,timeout=90);r.raise_for_status()
        if not r.text.startswith('/* DATA DESCRIPTION:') or '*/\nDate/Time\t' not in r.text:
            raise ValueError('Not a PANGAEA data table')
        tmp=path.with_suffix('.partial');tmp.write_bytes(r.content);tmp.replace(path)
        result=dict(source=record,url=url,sha256=sha(path),bytes=len(r.content),
                    retrieved_at=datetime.now(timezone.utc).isoformat())
        meta.write_text(json.dumps(result,indent=2));return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(one,inventory['records']))
    (out/'acquisition.json').write_text(json.dumps(records,indent=2))
    print('Acquired',len(records),'Payerne monthly UV/SW files',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--mode',choices=['public','cams','payerne'],required=True)
    parser.add_argument('--year',type=int)
    args=parser.parse_args()
    if args.mode == 'public': public(args.root)
    elif args.mode == 'payerne': payerne(args.root)
    else: cams(args.root,args.year)
