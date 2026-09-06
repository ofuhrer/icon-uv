"""Acquire daylight-complete drivers without modifying the earlier campaign."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'work/product-readiness-20260906'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observations(root, shard, shards):
    cfg=json.loads((root/'campaign.json').read_text())
    out=root/'observations';out.mkdir(exist_ok=True)
    records=[]
    for case in cfg['cases'][shard::shards]:
        date=datetime.fromisoformat(case['reference'].replace('Z','+00:00'))
        for day in (0,1):
            path=out/f'{date:%Y%m%d}_day{day}.csv'
            if not path.exists():
                start=date+timedelta(days=day,hours=4);end=date+timedelta(days=day,hours=21)
                temporary=path.with_suffix('.partial')
                command=['/oprusers/osm/opr.inn/bin/jretrievedwh','--stage','prod',
                         '--timeout','60','-s','surface','-i','nat_abbr,DAV',
                         '-n','gre000h0,sre000h0,prestah0,htoauths,rre150h0','-t',
                         f'{start:%Y%m%d%H%M},{end:%Y%m%d%H%M}','-r','1',
                         '--format','csv','-j','nat_abbr,lat,lon,elev','-o',str(temporary)]
                subprocess.run(command,check=True,timeout=90,capture_output=True)
                content=temporary.read_text()
                if '# ERROR' in content or not content.startswith('station;termin;'):
                    raise ValueError('DWH request failed')
                temporary.replace(path)
            records.append(dict(path=path.name,sha256=sha(path)))
    (out/f'acquisition_{shard}.json').write_text(json.dumps(dict(inputs=records),indent=2))


def cams(root,year):
    import cdsapi
    import eccodes as ec
    from icon_uv.data import cams_request,CAMS_DATASET
    old=ROOT/'work/scientific-multiyear-20260906/uv/woudc_manifest.json'
    available={r['case_date'] for r in json.loads(old.read_text())['inputs'] if r['status']=='downloaded'}
    cfg=json.loads((root/'campaign.json').read_text())
    dates=[(datetime.fromisoformat(c['date'])-timedelta(days=1)).strftime('%Y-%m-%d')
           for c in cfg['cases'] if c['year']==year and c['date'] in available]
    request=cams_request(dates[0]+'T12:00:00Z',range(12,61,3),(9.8,46.7,9.9,46.9));request['date']=dates
    out=root/'cams';out.mkdir(exist_ok=True)
    path=out/f'cams_{year}.grib';record=path.with_suffix('.json')
    if path.exists():
        saved=json.loads(record.read_text())
        if saved['request']!=request or saved['sha256']!=sha(path):raise ValueError('Changed CAMS input')
    else:
        temporary=path.with_suffix('.partial')
        client=cdsapi.Client(url='https://ads.atmosphere.copernicus.eu/api',retry_max=3,sleep_max=20,timeout=60)
        client.retrieve(CAMS_DATASET,request,str(temporary));temporary.replace(path)
        record.write_text(json.dumps(dict(dataset=CAMS_DATASET,request=request,sha256=sha(path),
                                         retrieved_at=datetime.now(timezone.utc).isoformat()),indent=2))
    split={}
    with path.open('rb') as stream:
        while (g:=ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(g,'dataTime')!=1200:raise ValueError('Wrong CAMS cycle')
                split.setdefault(ec.codes_get(g,'dataDate'),bytearray()).extend(ec.codes_get_message(g))
            finally:ec.codes_release(g)
    if {str(d) for d in split}!={d.replace('-','') for d in dates}:raise ValueError('Wrong CAMS dates')
    for date,data in split.items():
        target=out/f'cams_{date}_12.grib'
        if target.exists() and target.read_bytes()!=data:raise ValueError('Changed CAMS split')
        target.write_bytes(data)
    print('Retrieved',len(split),'complete-day CAMS cycles',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['observations','cams'])
    parser.add_argument('--root',type=Path,default=DEFAULT);parser.add_argument('--year',type=int)
    parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=1)
    args=parser.parse_args()
    if args.mode=='observations':observations(args.root,args.shard,args.shards)
    elif args.year in (2024,2025):cams(args.root,args.year)
    else:parser.error('CAMS year must be 2024 or 2025')
