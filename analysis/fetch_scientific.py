"""Acquire the bounded scientific extension; never changes archived inputs.

Run from the repository root. Existing inputs are reused; the frozen manifest
is verified rather than overwritten. Credentials stay with the CDS client.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/scientific-hardening-20260906'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def acquire_cams():
    import cdsapi
    import eccodes as ec
    from icon_uv.data import cams_request, CAMS_DATASET
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'cams_8cycles.grib'
    request = cams_request('2026-08-28T12:00:00Z', range(15, 31, 3), (5.3,45.2,17.5,48.6))
    request['date'] = '2026-08-28/2026-09-04'
    if not target.exists():
        client = cdsapi.Client(url='https://ads.atmosphere.copernicus.eu/api',
                               retry_max=3, sleep_max=20, timeout=60)
        temporary = target.with_suffix('.partial')
        client.retrieve(CAMS_DATASET, request, str(temporary))
        temporary.rename(target)
        (OUT/'cams_request.json').write_text(json.dumps(dict(dataset=CAMS_DATASET,
            request=request, retrieved_at=datetime.now(timezone.utc).isoformat(),
            sha256=sha(target)), indent=2)+'\n')
    split = {}
    with target.open('rb') as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                date, hour = ec.codes_get(handle,'dataDate'), ec.codes_get(handle,'dataTime')
                assert hour == 1200
                split.setdefault(str(date), bytearray()).extend(ec.codes_get_message(handle))
            finally:
                ec.codes_release(handle)
    assert len(split) == 8
    for date, content in split.items():
        path = OUT/f'cams_{date}_12.grib'
        if path.exists():
            assert path.read_bytes() == content
        else:
            path.write_bytes(content)
    print('CAMS: 8 daily cycles available', flush=True)


def acquire_public():
    from icon_uv.data import fetch_icon
    OUT.mkdir(parents=True, exist_ok=True)
    downloads_path=OUT/'downloads.json'
    records=json.loads(downloads_path.read_text()) if downloads_path.exists() else []
    jobs=[('uv_8days.json','https://uv-data.i-med.ac.at/public/data/?product=uve&start=2026-08-29&stop=2026-09-06'),
          ('uv_sites.json','https://uv-data.i-med.ac.at/public/sites/')]
    jobs += [(f'ogd-smn_{c}_h_recent.csv',f'https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/{c}/ogd-smn_{c}_h_recent.csv') for c in ['dav','wfj']]
    for name,url in jobs:
        path=OUT/name
        if path.exists(): continue
        response=requests.get(url,timeout=60); response.raise_for_status()
        path.write_bytes(response.content)
        records.append(dict(file=name,url=url,retrieved_at=datetime.now(timezone.utc).isoformat(),sha256=sha(path),bytes=path.stat().st_size))
        downloads_path.write_text(json.dumps(records,indent=2)+'\n')
    for cycle,first,last in [('00',4,18),('06',1,12),('12',1,6)]:
        path=OUT/f'icon_20260905_{cycle}.nc'
        if path.exists(): continue
        ds=fetch_icon(f'2026-09-05T{cycle}:00:00Z',first,last,bbox=(5.3,45.2,17.5,48.6),workers=3)
        encoding={v:{'units':'hours since 2026-09-05 00:00:00','calendar':'proleptic_gregorian'} for v in ['time','time_bounds']}
        ds.to_netcdf(path,encoding=encoding)
        print(path.relative_to(ROOT),flush=True)


def freeze():
    manifest_path=OUT/'frozen_inputs.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        for entry in manifest['inputs']:
            assert sha(ROOT/entry['path'])==entry['sha256'], f"Changed frozen input: {entry['path']}"
        print('Frozen input hashes verified; manifest retained')
        return
    old=ROOT/'work/scientific-validation-20260906'
    paths=[*OUT.glob('icon_*.nc'),*OUT.glob('cams_*.grib'),OUT/'uv_8days.json',OUT/'uv_sites.json',
           *OUT.glob('ogd-smn_*_h_recent.csv'),*old.glob('ogd-smn_*_h_now.csv'),
           old/'ogd-smn_meta_stations.csv',old/'ogd-smn_meta_parameters.csv',
           old/'uv-observations-fresh.json',ROOT/'work/uv_observation_day.nc',
           ROOT/'icon_uv/data/rt.npz']
    assert len(list(OUT.glob('icon_*.nc')))==3 and len(list(OUT.glob('cams_202*_12.grib')))==8
    manifest={'frozen_at':datetime.now(timezone.utc).isoformat(),
              'inputs':[dict(path=str(p.relative_to(ROOT)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(paths))]}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f"Frozen {len(paths)} inputs before evaluation")


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['public','cams','freeze'])
    {'public':acquire_public,'cams':acquire_cams,'freeze':freeze}[parser.parse_args().stage]()
