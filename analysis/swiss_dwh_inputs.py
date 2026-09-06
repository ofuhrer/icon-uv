"""Bounded, resumable Swiss DWH retrieval for the fixed ICON dates (Balfrin)."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def run(root, shard, shards):
    cfg=json.loads((root/'campaign.json').read_text())
    out=root/'observations';out.mkdir(exist_ok=True)
    records=[]
    for case in cfg['cases'][shard::shards]:
        date=datetime.fromisoformat(case['date'])
        path=out/f'{date:%Y%m%d}.csv';meta=path.with_suffix('.json')
        if path.exists() and meta.exists():
            r=json.loads(meta.read_text())
            if r['sha256'] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('Changed cached DWH input')
            records.append(r);continue
        tmp=path.with_suffix('.partial')
        command=['/oprusers/osm/opr.inn/bin/jretrievedwh','--stage','prod','--timeout','60',
                 '-s','surface','-i','nat_abbr,DAV,WFJ,PAY,JUN,OTL','-n',
                 'gre000h0,sre000h0,prestah0,htoauths,rre150h0,ouib02z0,ouib02t0,ouib02tq,ouib0bt0,ouib0btq',
                 '-t',f'{date:%Y%m%d}0300,{date+timedelta(days=1):%Y%m%d}2100',
                 '-r','1','--use-limitation','50','--format','csv',
                 '-j','nat_abbr,lat,lon,elev','-o',str(tmp)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=90)
        if result.returncode or not tmp.exists() or not tmp.read_text().startswith('station;termin;'):
            raise ValueError(f'DWH failed for {case["date"]}')
        tmp.replace(path)
        r=dict(date=case['date'],command=command,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               retrieved_at=datetime.now(timezone.utc).isoformat())
        meta.write_text(json.dumps(r,indent=2));records.append(r)
        print('Retrieved DWH',case['date'],flush=True)
    (out/f'acquisition_{shard}.json').write_text(json.dumps(records,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    a=p.parse_args();run(a.root,a.shard,a.shards)
