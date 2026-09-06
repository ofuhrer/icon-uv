"""Independent metadata alternatives; never select a favourable mapping."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

from analysis.swiss_uv_analysis import grids,halfhours
from analysis.multiyear import read_observations
from analysis.product_metrics import product_scores
from icon_uv.data import load_cams
from icon_uv.radiation import RadiationTable,solar_geometry


def run(root):
    old=root.parent/'product-readiness-20260906';cfg=json.loads((root/'campaign.json').read_text())
    oldcfg=json.loads((old/'campaign.json').read_text())
    source=Path(cfg['source_grid_file'])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=cfg['source_grid_sha256']:raise ValueError('Changed source grid')
    grid=xr.open_dataset(source);distance=(grid.latitude.values-46.81)**2+((grid.longitude.values-9.84)*np.cos(np.deg2rad(46.81)))**2
    davcell=int(grid.cell.values[np.argmin(distance)]);wfjcell=next(s['cell'] for s in oldcfg['stations'] if s['station']=='WFJ')
    frame=pd.read_csv(root/'results/daily_pairs.csv');frame=frame[(frame.reason=='usable')&(frame['product']=='native')&frame.site.isin(['Davos','Weissfluhjoch'])]
    table=RadiationTable();rows=[]
    for reference,g in frame.groupby('reference'):
        date=pd.Timestamp(reference).tz_localize(None);stem=f'{date:%Y%m%d}'
        raw=np.load(old/'icon'/f'{stem}_00.npz');meta=json.loads((old/'icon'/f'{stem}_00.json').read_text())
        cams=load_cams(root/'cams'/f'cams_{date-pd.Timedelta(days=1):%Y%m%d}_12.grib')
        obs=read_observations(root/'observations'/f'{stem}.csv')
        for r in g.itertuples():
            site=dict(next(s for s in cfg['stations'] if s['station']==r.site));valid=pd.Timestamp(r.valid_date)
            starts=pd.date_range(valid+pd.Timedelta(hours=3),periods=36,freq='30min');z,_,_=solar_geometry((starts+pd.Timedelta(minutes=15)).to_numpy(),site['latitude'],site['longitude'])
            if r.site=='Davos':site.update(latitude=46.81,longitude=9.84);cell=davcell;variant='WMO facility coordinates'
            else:cell=wfjcell;variant='Nearby SMN cell, unchanged UV geometry'
            col=int(np.flatnonzero(raw['cell']==cell)[0]);outputs,_,_=grids(date,r.day,site,col,raw,meta,cams,table,obs)
            pred=halfhours(outputs['native'],table);new=float(pred[z<90].max())
            rows.append(dict(site=r.site,reference=reference,valid_date=r.valid_date,season=r.season,day=r.day,variant=variant,cell=cell,
                             observed_uvi=r.observed_uvi,primary_uvi=r.predicted_uvi,alternative_uvi=new,delta_uvi=new-r.predicted_uvi))
        raw.close()
    frame=pd.DataFrame(rows);frame.to_csv(root/'results/spatial_pairs.csv',index=False);summaries=[]
    for (site,day),g in frame.groupby(['site','day']):
        a=np.floor(g.primary_uvi+.5);b=np.floor(g.alternative_uvi+.5)
        summaries.append(dict(site=site,day=int(day),n=len(g),mean_abs_change=float(abs(g.delta_uvi).mean()),
                  p95_abs_change=float(abs(g.delta_uvi).quantile(.95)),max_abs_change=float(abs(g.delta_uvi).max()),
                  displayed_changed=float(np.mean(a!=b)),category_changed=float(np.mean(np.searchsorted([3,6,8,11],a,side='right')!=np.searchsorted([3,6,8,11],b,side='right'))),
                  primary_scores=product_scores(g.observed_uvi,g.primary_uvi),alternative_scores=product_scores(g.observed_uvi,g.alternative_uvi)))
    (root/'results/spatial_sensitivity.json').write_text(json.dumps(summaries,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root)
