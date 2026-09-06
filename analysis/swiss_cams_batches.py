"""Recover a slow bulk CAMS request with identical, bounded monthly subsets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import cdsapi
import eccodes as ec
from icon_uv.data import cams_request,CAMS_DATASET


def run(root,year):
    cfg=json.loads((root/'campaign.json').read_text());out=root/'cams';batches={}
    for c in cfg['cases']:
        if c['year']!=year:continue
        date=datetime.fromisoformat(c['date'])-timedelta(days=1)
        batches.setdefault(date.strftime('%Y%m'),[]).append(date.strftime('%Y-%m-%d'))
    def one(item):
        month,dates=item;request=cams_request(dates[0]+'T12:00:00Z',range(12,61,3),(6.8,46.0,10.0,47.0));request['date']=dates
        path=out/f'cams_batch_{month}.grib';meta=path.with_suffix('.json')
        if path.exists():
            old=json.loads(meta.read_text())
            if old['request']!=request or old['sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Changed CAMS batch')
        else:
            tmp=path.with_suffix('.partial')
            client=cdsapi.Client(url='https://ads.atmosphere.copernicus.eu/api',retry_max=3,sleep_max=20,timeout=60)
            client.retrieve(CAMS_DATASET,request,str(tmp));tmp.replace(path)
            meta.write_text(json.dumps(dict(request=request,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),dataset=CAMS_DATASET,retrieved_at=datetime.now(timezone.utc).isoformat()),indent=2))
        split={}
        with path.open('rb') as stream:
            while (g:=ec.codes_grib_new_from_file(stream)) is not None:
                try:
                    if ec.codes_get(g,'dataTime')!=1200:raise ValueError('Wrong CAMS cycle')
                    split.setdefault(ec.codes_get(g,'dataDate'),bytearray()).extend(ec.codes_get_message(g))
                finally:ec.codes_release(g)
        if {str(k) for k in split}!={d.replace('-','') for d in dates}:raise ValueError('Wrong CAMS dates')
        for date,body in split.items():
            target=out/f'cams_{date}_12.grib'
            if target.exists() and target.read_bytes()!=body:raise ValueError('Changed CAMS split')
            if not target.exists():
                tmp=target.with_suffix('.partial');tmp.write_bytes(body);tmp.replace(target)
        print('Completed monthly CAMS batch',month,len(split),flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(one,batches.items()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--year',type=int,required=True)
    a=p.parse_args();run(a.root,a.year)
