"""Acquire public WOUDC observations and bounded historical CAMS inputs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import argparse

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/scientific-multiyear-20260906/uv'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observations():
    cfg=json.loads((OUT.parent/'campaign.json').read_text())
    directory=OUT/'woudc';directory.mkdir(parents=True,exist_ok=True)
    base='https://woudc.org/archive/Archive-NewFormat/Broad-band_1.0_1/stn501/uv-biometer/'
    available={}
    for year in (2024,2025,2026):
        response=requests.get(f'{base}{year}/',timeout=30)
        response.raise_for_status() if response.status_code != 404 else None
        (directory/f'index_{year}.html').write_bytes(response.content)
        available[year]=set(re.findall(r'href="([^"]+\.csv)"',response.text)) if response.status_code==200 else set()
    jobs=[]
    for case in cfg['cases']:
        for day in (0,1):
            date=datetime.fromisoformat(case['reference'].replace('Z','+00:00'))+timedelta(days=day)
            jobs.append((case['date'],day,date))
    def fetch(job):
        case,day,date=job
        name=f'{date:%Y%m%d}.UV-Biometer.501A.1492.PMOD-WRC.csv'
        record=dict(case_date=case,day=day,date=str(date.date()),url=f'{base}{date.year}/{name}')
        if name not in available[date.year]:
            return dict(record,status='not_listed')
        path=directory/name
        if not path.exists():
            response=requests.get(record['url'],timeout=30);response.raise_for_status()
            path.write_bytes(response.content)
        return dict(record,status='downloaded',path=name,sha256=sha(path))
    with ThreadPoolExecutor(max_workers=3) as pool:
        result=list(pool.map(fetch,jobs))
    (OUT/'woudc_manifest.json').write_text(json.dumps(dict(retrieved_at=datetime.now(timezone.utc).isoformat(),inputs=result),indent=2))
    print('WOUDC:',sum(r['status']=='downloaded' for r in result),'of',len(result),'requested files',flush=True)


def cams(year):
    import cdsapi
    import eccodes as ec
    from icon_uv.data import cams_request,CAMS_DATASET
    cfg=json.loads((OUT.parent/'campaign.json').read_text())
    dates=[(datetime.fromisoformat(c['reference'].replace('Z','+00:00'))-timedelta(days=1)).strftime('%Y-%m-%d')
           for c in cfg['cases'] if c['year']==year]
    request=cams_request(dates[0]+'T12:00:00Z',range(18,55,3),(9.8,46.7,9.9,46.9))
    request['date']=dates
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f'cams_{year}.grib'
    if not path.exists():
        client=cdsapi.Client(url='https://ads.atmosphere.copernicus.eu/api',retry_max=3,sleep_max=20,timeout=60)
        temporary=path.with_suffix('.partial')
        client.retrieve(CAMS_DATASET,request,str(temporary))
        temporary.rename(path)
        (OUT/f'cams_{year}_request.json').write_text(json.dumps(dict(dataset=CAMS_DATASET,request=request,
            retrieved_at=datetime.now(timezone.utc).isoformat(),sha256=sha(path)),indent=2))
    split={}
    with path.open('rb') as stream:
        while (g:=ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(g,'dataTime')!=1200:raise ValueError('Unexpected CAMS cycle')
                date=ec.codes_get(g,'dataDate')
                split.setdefault(date,bytearray()).extend(ec.codes_get_message(g))
            finally:ec.codes_release(g)
    if {str(d).replace('-','') for d in dates}!={str(d) for d in split}:raise ValueError('CAMS dates differ from request')
    for date,content in split.items():
        target=OUT/f'cams_{date}_12.grib'
        if target.exists() and target.read_bytes()!=content:raise ValueError('Existing CAMS input changed')
        target.write_bytes(content)
    print('CAMS:',len(split),'cycles',flush=True)


def freeze():
    from analysis.scientific import verify_inputs
    target=OUT/'frozen_inputs.json'
    if target.exists():
        verify_inputs(OUT,target)
        return
    for year in (2024,2025):
        metadata=json.loads((OUT/f'cams_{year}_request.json').read_text())
        if sha(OUT/f'cams_{year}.grib')!=metadata['sha256']:raise ValueError('Changed CAMS download')
    manifest=json.loads((OUT/'woudc_manifest.json').read_text())
    for record in manifest['inputs']:
        if record['status']=='downloaded' and sha(OUT/'woudc'/record['path'])!=record['sha256']:
            raise ValueError('Changed WOUDC input')
    files=sorted(OUT.glob('*.grib'))+sorted(OUT.glob('cams_*_request.json'))
    files+=[OUT/'woudc_manifest.json']+sorted((OUT/'woudc').glob('*'))
    document=dict(inputs=[dict(path=str(p.relative_to(OUT)),sha256=sha(p)) for p in files],
                  protocol_sha256=sha(ROOT/'analysis/MULTIYEAR_UV_PLAN.md'),
                  table_sha256=sha(ROOT/'icon_uv/data/rt.npz'),
                  created=datetime.now(timezone.utc).isoformat())
    target.write_text(json.dumps(document,indent=2));verify_inputs(OUT,target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['observations','cams','freeze'])
    parser.add_argument('--year',type=int,choices=[2024,2025])
    args=parser.parse_args()
    if args.mode=='observations':observations()
    elif args.mode=='freeze':freeze()
    elif args.year is None:parser.error('--year is required for CAMS')
    else:cams(args.year)
