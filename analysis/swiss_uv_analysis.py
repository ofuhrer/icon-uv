"""Fixed-method Swiss UV comparisons on matched half-hour supports."""
import argparse
from functools import lru_cache
import hashlib
import io
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

from icon_uv.data import load_cams
from icon_uv.radiation import RadiationTable, solar_geometry
from icon_uv.daily import daily_cells
from analysis.multiyear import read_observations, reconstructed_sw
from analysis.scientific import uv_series, sunshine_regime
from analysis.product_metrics import product_scores, score_intervals, date_block_indices

ROOT=Path(__file__).resolve().parents[1]
PRODUCTS=('native','gray','bright','snow','measured_sw','measured_sw_gray')
SEASONS={12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'}


def interval_means(series, starts, duration=1800, phase=0):
    """Integrate centred 60-second means, retaining every gap/invalid interval.

    phase=-30 treats the source timestamp as interval end; +30 as start.
    No resampling interpolation or partial-window normalization is performed.
    """
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError('Unordered or duplicate observation time')
    t=series.index.to_numpy().astype('datetime64[s]').astype(np.int64)+phase-30
    values=series.to_numpy(float)
    answer=np.full(len(starts),np.nan)
    for j,start in enumerate(np.asarray(starts).astype('datetime64[s]').astype(np.int64)):
        end=start+duration
        left=np.searchsorted(t+60,start,side='right');right=np.searchsorted(t,end,side='left')
        if right<=left:continue
        tt=t[left:right];vv=values[left:right]
        widths=np.minimum(tt+60,end)-np.maximum(tt,start)
        if (widths.sum()!=duration or np.any(np.diff(tt)!=60) or
                not np.isfinite(vv).all() or np.any(vv<0)):
            continue
        answer[j]=np.dot(widths,vv)/duration
    return answer


@lru_cache(maxsize=32)
def payerne_series(root, month, kind):
    path=Path(root)/'payerne'/f'{month}_{kind}.tab'
    if not path.exists():return None,False
    meta=json.loads(path.with_suffix('.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:
        raise ValueError('Changed Payerne source')
    text=path.read_text();frame=pd.read_csv(io.StringIO(text.split('*/\n',1)[1]),sep='\t')
    frame.index=pd.to_datetime(frame['Date/Time'])
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError('Invalid Payerne timestamps')
    name='UV-b global' if kind=='uv' else 'SWD'
    unit='[W/m**2]';value=frame[f'{name} {unit}'].astype(float)
    lo=frame[f'{name}, min {unit}'] if kind=='uv' else frame[f'{name} min {unit}']
    hi=frame[f'{name}, max {unit}'] if kind=='uv' else frame[f'{name} max {unit}']
    std=frame[f'{name} std dev {unit}']
    tolerance=1e-5 if kind=='uv' else 1.0
    bad=(value<0)|(lo.notna()&(value<lo-tolerance))|(hi.notna()&(value>hi+tolerance))|(std<0)
    # Broad extraterrestrial irradiance bound for SW, independent of ICON.
    if kind=='sw':bad|=value>1600
    value=value.mask(bad)
    identified=any(f['name']==name and f['instrument'] for f in meta['source']['fields'])
    return value*(40 if kind=='uv' else 1),bool(identified)


def grids(date,day,site,col,raw,provenance,cams,table,observations,bsrn_sw=None):
    leads=list(range(3+day*24,22+day*24));indices=[list(raw['leads']).index(h) for h in leads]
    starts=date+pd.to_timedelta(np.array(leads[:-1]),unit='h')
    midpoints=(starts+pd.Timedelta(minutes=30)).to_numpy()
    sw=reconstructed_sw(raw,provenance['records'],leads)[:,col]
    pressure=(raw['pressure'][indices[:-1],col]+raw['pressure'][indices[1:],col])/2
    pressure*=np.exp(-(site['altitude_m']-raw['height'][col])/8434)
    albedo=(raw['albedo'][indices[:-1],col]+raw['albedo'][indices[1:],col])/200
    coords=(cams.time.values.astype('datetime64[s]').astype(float),cams.latitude.values,cams.longitude.values)
    points=np.column_stack([midpoints.astype('datetime64[s]').astype(float),
                            np.full(18,site['latitude']),np.full(18,site['longitude'])])
    ozone,aod=[RegularGridInterpolator(coords,cams[k].values,bounds_error=True)(points) for k in ('ozone_du','aod550')]
    times=starts.to_numpy()[None,:]+(np.arange(12)[:,None]*300+150).astype('timedelta64[s]')
    z,_,distance=solar_geometry(times,site['latitude'],site['longitude'])
    clear=(table.at(z,ozone,pressure,aod,albedo,0)[...,:2].sum(axis=-1)*distance).mean(axis=0)
    smn=site.get('nearby_smn',site['station'])
    obs=np.array([observations.loc[(smn,t+pd.Timedelta(hours=1)),'gre000h0']
          if (smn,t+pd.Timedelta(hours=1)) in observations.index and
          observations.loc[(smn,t+pd.Timedelta(hours=1)),'gre000h0_quality']==4 else np.nan for t in starts])
    if bsrn_sw is not None:obs=interval_means(bsrn_sw,starts.to_numpy(),duration=3600)
    outputs={}
    for label in PRODUCTS:
        input_sw=obs if label.startswith('measured_sw') else sw
        available=np.isfinite(input_sw)&(input_sw>=0)
        night=np.all(z>=90,axis=0)
        available|=night
        if not np.any(available&~night):continue
        # Placeholders permit vector evaluation only; unavailable daylight never scores.
        input_sw=np.where(night|~available,0,input_sw)
        tau,scale,flags=table.cloud(z,distance,ozone,pressure,aod,albedo,input_sw)
        if label in ('gray','measured_sw_gray'):
            if np.any((clear<5)&(input_sw>5)):continue
            tau=np.zeros(18);scale=np.divide(input_sw,clear,out=np.zeros(18),where=clear>0)
        uv_albedo=.15 if label=='bright' else .8 if label=='snow' else .05
        ds=xr.Dataset(coords={'time':midpoints,'cell':[int(raw['cell'][col])]})
        ds['time_bounds']=(('time','bounds'),np.column_stack([starts.to_numpy(),(starts+pd.Timedelta(hours=1)).to_numpy()]))
        for k,v in [('ozone_du',ozone),('aod550',aod),('pressure_pa',pressure),('uv_albedo',np.full(18,uv_albedo)),
                    ('effective_cloud_tau550',tau),('cloud_scale',scale),('quality_flag',flags)]:
            ds[k]=(('time','cell'),v[:,None]);ds[k].attrs['units']='Pa' if k=='pressure_pa' else 'DU' if k=='ozone_du' else '1'
        for k in ('latitude','longitude','altitude_m'):ds[k]=('cell',[site[k]])
        ds.attrs['radiation_table_sha256']=table.sha256
        ds['sw_available']=('time',available)
        outputs[label]=ds
    return outputs,sw,obs


def halfhours(grid,table):
    starts=grid.time_bounds.values[:,0]
    times=starts[:,None]+(np.arange(12)*300+150).astype('timedelta64[s]')
    z,_,distance=solar_geometry(times,grid.latitude.item(),grid.longitude.item())
    args=[grid[k].values for k in ('ozone_du','pressure_pa','aod550','uv_albedo','effective_cloud_tau550')]
    uv=40*table.at(z,*args)[...,2:].sum(axis=-1)*distance*grid.cloud_scale.values
    if not np.isfinite(uv).all() or np.any(uv<0):raise ValueError('Invalid model UVI')
    result=uv.reshape(-1,6).mean(axis=1)
    return np.where(np.repeat(grid.sw_available.values,2),result,np.nan)


def run(root,limit=None,wait_seconds=0):
    cfg=json.loads((root/'campaign.json').read_text());table=RadiationTable()
    out=root/'results';out.mkdir(exist_ok=True);daily=[];windows=[];errors=[]
    reservation={r['date'] for r in json.loads((ROOT/'work/product-readiness-20260906/payerne_reserved.json').read_text())['cases']}
    for case in cfg['cases'][:limit]:
        date=pd.Timestamp(case['date']);stem=f'{date:%Y%m%d}'
        rawpath=root/'icon'/f'{stem}_00.npz'
        needed=[rawpath,rawpath.with_suffix('.json'),root/'observations'/f'{stem}.csv',
                root/'cams'/f'cams_{date-pd.Timedelta(days=1):%Y%m%d}_12.grib']
        deadline=time.monotonic()+wait_seconds
        while any(not p.exists() for p in needed) and time.monotonic()<deadline:
            time.sleep(10)
        if not rawpath.exists():raise FileNotFoundError(rawpath)
        raw=np.load(rawpath);provenance=json.loads(rawpath.with_suffix('.json').read_text())
        if hashlib.sha256(rawpath.read_bytes()).hexdigest()!=provenance['output_sha256']:raise ValueError('Changed native input')
        cams=load_cams(root/'cams'/f'cams_{date-pd.Timedelta(days=1):%Y%m%d}_12.grib')
        if pd.Timestamp(cams.attrs['forecast_reference_time']).tz_localize(None)!=date-pd.Timedelta(hours=12):raise ValueError('Wrong CAMS cycle')
        obs=read_observations(root/'observations'/f'{stem}.csv')
        imed=json.loads((root/'imed'/f'{stem}.json').read_text())
        for col,original in enumerate(cfg['stations']):
            if original['station'] not in ('Davos','Weissfluhjoch','PAY'):continue
            site=dict(original)
            if site['station']=='PAY':site.update(latitude=46.8123,longitude=6.9422,altitude_m=493)
            for day in (0,1):
                valid=date+pd.Timedelta(days=day);starts=pd.date_range(valid+pd.Timedelta(hours=3),periods=36,freq='30min')
                mid=starts+pd.Timedelta(minutes=15);z,_,_=solar_geometry(mid.to_numpy(),site['latitude'],site['longitude'])
                required=z<90;central=z<=70
                base=dict(reference=case['reference'],case_date=case['date'],valid_date=str(valid.date()),
                          season=SEASONS[valid.month],year=valid.year,day=day,site=site['station'],
                          configuration=provenance['configuration'],cell=site['cell'],distance_km=site['distance_km'],
                          terrain_height=float(raw['height'][col]),instrument_height=site['altitude_m'],
                          observed_uvi=np.nan,predicted_uvi=np.nan,rolling_predicted_uvi=np.nan,
                          rolling_observed_uvi=np.nan,rolling_phase_low=np.nan,rolling_phase_high=np.nan,
                          observed_phase_low=np.nan,observed_phase_high=np.nan,
                          snow_regime='Unknown snow',sunshine_regime='Unknown sunshine')
                reason='usable';phase_values=None;bsrn_sw=None;uv=None
                if site['station']=='PAY':
                    uv,identified=payerne_series(str(root),f'{valid:%Y%m}','uv')
                    bsrn_sw,_=payerne_series(str(root),f'{valid:%Y%m}','sw')
                    if case['date'] not in reservation:reason='outside_reserved_period'
                    elif uv is None:reason='missing_archive'
                    elif not identified:reason='missing_instrument_metadata'
                    values=interval_means(uv,starts.to_numpy()) if uv is not None else np.full(36,np.nan)
                    if uv is not None:phase_values=np.array([interval_means(uv,starts.to_numpy(),phase=p) for p in (-30,0,30)])
                    base['sw_reference']='BSRN PAY' if bsrn_sw is not None else 'nearby DWH PAY'
                else:
                    series=uv_series(imed,site['station']);values=series.reindex(mid).to_numpy(float)
                    if not len(series):reason='missing_archive'
                    base['sw_reference']='nearby DWH '+site['nearby_smn']
                good=required&np.isfinite(values)&(values>=0)
                base.update(required_windows=int(required.sum()),available_windows=int(good.sum()),
                            central_required=int(central.sum()),central_available=int((central&good).sum()))
                # Classification uses the fixed local noon hour, never the observed peak.
                key=(site.get('nearby_smn',site['station']),valid+pd.Timedelta(hours=12))
                if key in obs.index:
                    r=obs.loc[key]
                    if r.htoauths_quality==4:base['snow_regime']='Measured snow' if r.htoauths>0 else 'Snow-free' if r.htoauths==0 else 'Unknown snow'
                    if r.sre000h0_quality==4:base['sunshine_regime']=sunshine_regime(np.array([r.sre000h0]))[0]
                outputs={}
                if reason=='usable':
                    outputs,sw,measured=grids(date,day,site,col,raw,provenance,cams,table,obs,bsrn_sw)
                    base['sw_bias']=float(np.mean(sw-measured)) if np.isfinite(measured).all() else np.nan
                    if uv is not None and good[required].all():
                        rolling_starts=pd.date_range(valid+pd.Timedelta(hours=3),valid+pd.Timedelta(hours=20,minutes=30),freq='5min')
                        rz,_,_=solar_geometry((rolling_starts+pd.Timedelta(minutes=15)).to_numpy(),site['latitude'],site['longitude'])
                        rolling_starts=rolling_starts[rz<90]
                        phase_peaks=np.array([interval_means(uv,rolling_starts.to_numpy(),phase=p).max() for p in (-30,0,30)])
                        base.update(rolling_observed_uvi=phase_peaks[1],rolling_phase_low=phase_peaks.min(),rolling_phase_high=phase_peaks.max())
                for product in PRODUCTS:
                    row=dict(base,product=product,reason=reason)
                    if reason=='usable':
                        if product not in outputs:row['reason']='unavailable_sw_substitution'
                        else:
                            pred=halfhours(outputs[product],table)
                            for i in np.flatnonzero(good&np.isfinite(pred)):
                                windows.append(dict(reference=base['reference'],valid_date=base['valid_date'],season=base['season'],
                                   year=base['year'],day=day,site=site['station'],product=product,time=str(mid[i]),zenith=float(z[i]),
                                   observed_uvi=values[i],predicted_uvi=pred[i]))
                            if not good[required].all():row['reason']='incomplete_observed_daylight'
                            elif not np.isfinite(pred[required]).all():row['reason']='incomplete_sw_daylight'
                            else:
                                row.update(observed_uvi=float(values[required].max()),predicted_uvi=float(pred[required].max()))
                                result=daily_cells(outputs[product],base['valid_date'],table)
                                if not result['available'][0]:row['reason']='incomplete_model_daylight'
                                row['rolling_predicted_uvi']=result['uvi'][0]
                                row['quality_flag']=int(result['quality_flag'][0])
                                if phase_values is not None:
                                    peaks=np.max(phase_values[:,required],axis=1)
                                    row['observed_phase_low']=float(peaks.min());row['observed_phase_high']=float(peaks.max())
                    daily.append(row)
        raw.close();print('Processed',case['date'],flush=True)
    frame=pd.DataFrame(daily);frame.to_csv(out/'daily_pairs.csv',index=False)
    pairs=pd.DataFrame(windows);pairs.to_csv(out/'window_pairs.csv',index=False)
    (out/'errors.json').write_text(json.dumps(errors,indent=2))
    summarize(root,frame,pairs)


def summarize(root,frame,pairs):
    # Older in-flight runs already computed valid pairs before this metadata fix.
    if 'year' not in pairs:
        pairs=pairs.assign(year=pd.to_datetime(pairs.valid_date).dt.year)
        pairs.to_csv(root/'results/window_pairs.csv',index=False)
    out=root/'results';summaries=[]
    for source,target in [(frame[frame.reason=='usable'],'daily_halfhour_grid'),(pairs,'paired_halfhours'),(pairs[pairs.zenith<=70],'paired_central_sun')]:
        for fields in [('site','day','product'),('site','day','product','season'),('site','day','product','year')]:
            for key,g in source.groupby(list(fields)):
                r=dict(zip(fields,key));r.update(target=target,stratum='/'.join(fields),dates=g.valid_date.nunique(),**product_scores(g.observed_uvi,g.predicted_uvi))
                r['rmse']=float(np.sqrt(np.mean((g.predicted_uvi-g.observed_uvi)**2)));summaries.append(r)
    for field in ['snow_regime','sunshine_regime','configuration']:
        for key,g in frame[frame.reason=='usable'].groupby(['site','day','product',field]):
            r=dict(zip(['site','day','product',field],key));r.update(target='daily_halfhour_grid',stratum='site/day/product/'+field,dates=g.valid_date.nunique(),**product_scores(g.observed_uvi,g.predicted_uvi));summaries.append(r)
    pd.DataFrame(summaries).to_csv(out/'scores.csv',index=False)
    frame.groupby(['site','day','product','reason']).size().rename('count').to_csv(out/'coverage.csv')
    confidence=[];comparisons=[]
    good=frame[frame.reason=='usable']
    for (site,day,product),g in good.groupby(['site','day','product']):
        if product in ('native','gray','measured_sw'):
            confidence.append(dict(site=site,day=int(day),product=product,block=3,dates=g.valid_date.nunique(),intervals=score_intervals(g,block=3)))
    for (site,day),g in good.groupby(['site','day']):
        for left,right in [('native','gray'),('native','measured_sw')]:
            paired=g[g['product']==left].merge(g[g['product']==right],on=['valid_date','season'],suffixes=('_left','_right'))
            if not len(paired):continue
            delta=(abs(paired.predicted_uvi_left-paired.observed_uvi_left)-abs(paired.predicted_uvi_right-paired.observed_uvi_right)).to_numpy()
            boot=[float(delta[i].mean()) for i in date_block_indices(paired.valid_date,paired.season)]
            comparisons.append(dict(site=site,day=int(day),left=left,right=right,dates=paired.valid_date.nunique(),delta_mae=float(delta.mean()),ci95=np.quantile(boot,[.025,.975]).tolist()))
    (out/'confidence.json').write_text(json.dumps(confidence,indent=2))
    (out/'paired_comparisons.json').write_text(json.dumps(comparisons,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--limit',type=int)
    p.add_argument('--wait-seconds',type=int,default=0)
    a=p.parse_args();run(a.root,a.limit,a.wait_seconds)
