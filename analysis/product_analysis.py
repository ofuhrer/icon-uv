"""Full-day retrospective UV baseline and measured-SW attribution."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator
import xarray as xr

from icon_uv.daily import daily_cells,daylight_hours,local_day_bounds
from icon_uv.data import load_cams
from icon_uv.radiation import RadiationTable,solar_geometry
from analysis.multiyear import read_observations,reconstructed_sw
from analysis.multiyear_uv import read_woudc,source_cadence
from analysis.product_metrics import product_scores,score_intervals,date_block_indices
from analysis.scientific import verify_inputs,sunshine_regime

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'work/product-readiness-20260906'
OLD=ROOT/'work/scientific-multiyear-20260906'
OUTPUT=INPUT/'results'
PRODUCTS=('native','gray','measured_sw','measured_sw_gray','bright','snow')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_inputs():
    path=INPUT/'frozen_inputs.json'
    if path.exists():
        verify_inputs(INPUT,path);return
    cfg=json.loads((INPUT/'campaign.json').read_text())
    files=[INPUT/'campaign.json']
    for case in cfg['cases']:
        stem=case['date'].replace('-','')+'_00'
        array=INPUT/'icon'/f'{stem}.npz';record=array.with_suffix('.json')
        meta=json.loads(record.read_text())
        if sha(array)!=meta['output_sha256'] or meta['campaign_sha256']!=sha(INPUT/'campaign.json'):
            raise ValueError('Native acquisition identity mismatch')
        files.extend([array,record])
        files.extend(INPUT/'observations'/f"{case['date'].replace('-','')}_day{day}.csv" for day in (0,1))
    for path in sorted((INPUT/'cams').glob('cams_20??.json')):
        if sha(path.with_suffix('.grib'))!=json.loads(path.read_text())['sha256']:raise ValueError('CAMS input changed')
    woudc=json.loads((OLD/'uv/woudc_manifest.json').read_text())['inputs']
    for case_date in {r['case_date'] for r in woudc if r['status']=='downloaded'}:
        cycle=pd.Timestamp(case_date)-pd.Timedelta(days=1)
        if not (INPUT/'cams'/f'cams_{cycle:%Y%m%d}_12.grib').exists():raise ValueError('Missing complete-day CAMS input')
    files.extend(sorted((INPUT/'cams').glob('*')))
    files.extend(sorted((INPUT/'observations').glob('acquisition_*.json')))
    if not all(p.is_file() for p in files):raise ValueError('Incomplete product inputs')
    document=dict(inputs=[dict(path=str(p.relative_to(INPUT)),sha256=sha(p)) for p in files],
                  external={str(p.relative_to(ROOT)):sha(p) for p in
                            [ROOT/'analysis/PRODUCT_CONTRACT_V1.md',ROOT/'analysis/PRODUCT_ANALYSIS_PLAN.md',
                             ROOT/'icon_uv/data/rt.npz',OLD/'uv/frozen_inputs.json']})
    (INPUT/'frozen_inputs.json').write_text(json.dumps(document,indent=2))
    verify_inputs(INPUT,INPUT/'frozen_inputs.json')


def observed_peak(series,valid_date,latitude=46.82,longitude=9.85):
    """Exact piecewise-linear raw integration, with full daylight completeness."""
    _,gap=source_cadence(series)
    hours,required=daylight_hours(valid_date,np.array([latitude]),np.array([longitude]))
    active=hours[required[:,0]]
    if not len(active):return dict(uvi=0.,hourly=0.,peak_start=hours[0],reason='usable')
    lo,hi=active[0],active[-1]+np.timedelta64(1,'h')
    times=series.index.to_numpy().astype('datetime64[ns]')
    left=np.searchsorted(times,lo,side='right')-1;right=np.searchsorted(times,hi,side='left')
    if left<0 or right>=len(times):return dict(reason='missing_daylight_bracket')
    t=times[left:right+1].astype('datetime64[ms]').astype(float)/1000
    y=series.to_numpy()[left:right+1]
    if not np.isfinite(y).all() or np.any(y<0):return dict(reason='invalid_daylight_irradiance')
    dx=np.diff(t)
    if np.any(dx>gap):return dict(reason='daylight_observation_gap')
    cumulative=np.r_[0,np.cumsum((y[1:]+y[:-1])*.5*dx)]
    def integral_at(query):
        q=query.astype('datetime64[ms]').astype(float)/1000
        i=np.clip(np.searchsorted(t,q,side='right')-1,0,len(t)-2)
        dt=q-t[i];slope=(y[i+1]-y[i])/dx[i]
        return cumulative[i]+y[i]*dt+.5*slope*dt*dt
    start,end=local_day_bounds(valid_date)
    edges=np.arange(start,end+np.timedelta64(5,'m'),np.timedelta64(5,'m'))
    values=np.zeros(len(edges)-1)
    eligible=(edges[:-1]>=lo)&(edges[1:]<=hi)
    values[eligible]=(integral_at(edges[1:][eligible])-integral_at(edges[:-1][eligible]))/300
    window=np.lib.stride_tricks.sliding_window_view(values,6).mean(axis=-1)
    peak=int(window.argmax())
    return dict(uvi=float(window[peak]),hourly=float(values.reshape(-1,12).mean(axis=1).max()),
                peak_start=edges[peak],reason='usable',daylight_hours=len(active))


def make_grid(date,day,site,raw,provenance,cams,table,observations):
    leads=list(range(3+day*24,22+day*24));indices=[list(raw['leads']).index(h) for h in leads]
    col=len(raw['cell'])-1
    starts=date+pd.to_timedelta(np.array(leads[:-1]),unit='h');midpoints=(starts+pd.Timedelta(minutes=30)).to_numpy()
    sw=reconstructed_sw(raw,provenance['records'],leads)[:,col]
    pressure=(raw['pressure'][indices[:-1],col]+raw['pressure'][indices[1:],col])/2*np.exp(-(site['altitude_m']-raw['height'][col])/8434)
    albedo=(raw['albedo'][indices[:-1],col]+raw['albedo'][indices[1:],col])/200
    coords=(cams.time.values.astype('datetime64[s]').astype(float),cams.latitude.values,cams.longitude.values)
    points=np.column_stack([midpoints.astype('datetime64[s]').astype(float),np.full(18,site['latitude']),np.full(18,site['longitude'])])
    ozone,aod=[RegularGridInterpolator(coords,cams[k].values,bounds_error=True)(points) for k in ('ozone_du','aod550')]
    times=starts.to_numpy()[None,:]+(np.arange(12)[:,None]*300+150).astype('timedelta64[s]')
    z,_,distance=solar_geometry(times,site['latitude'],site['longitude'])
    clear=table.at(z,ozone,pressure,aod,albedo,0)[...,:2].sum(axis=-1)*distance
    clear=clear.mean(axis=0)
    obs=np.array([observations.loc[('DAV',t+pd.Timedelta(hours=1)),'gre000h0']
                  if ('DAV',t+pd.Timedelta(hours=1)) in observations.index and observations.loc[('DAV',t+pd.Timedelta(hours=1)),'gre000h0_quality']==4 else np.nan for t in starts])
    outputs={}
    for label in PRODUCTS:
        input_sw=obs if label.startswith('measured_sw') else sw
        if not np.isfinite(input_sw).all() or np.any(input_sw<0):continue
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
        outputs[label]=ds
    return outputs,sw,obs


def run():
    freeze_inputs();verify_inputs(OLD/'uv',OLD/'uv/frozen_inputs.json')
    for path,expected in json.loads((INPUT/'frozen_inputs.json').read_text())['external'].items():
        if sha(ROOT/path)!=expected:raise ValueError('Changed frozen protocol/reference')
    OUTPUT.mkdir(exist_ok=True)
    cfg=json.loads((INPUT/'campaign.json').read_text());site=cfg['uv_stations'][0]
    manifest=json.loads((OLD/'uv/woudc_manifest.json').read_text())['inputs']
    table=RadiationTable();rows=[];errors=[]
    for case in cfg['cases']:
        date=pd.Timestamp(case['date'])
        with np.load(INPUT/'icon'/f'{date:%Y%m%d}_00.npz') as raw:
            provenance=json.loads((INPUT/'icon'/f'{date:%Y%m%d}_00.json').read_text())
            for day in (0,1):
                valid=str((date+pd.Timedelta(days=day)).date());season={12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'}[pd.Timestamp(valid).month]
                base=dict(reference=case['reference'],valid_date=valid,day=day,season=season,site='WOUDC501-1492',configuration=provenance['configuration'],
                          observed_uvi=np.nan,observed_hourly_max=np.nan,predicted_uvi=np.nan,hourly_max=np.nan,snow_regime='Unknown snow',sunshine_regime='Unknown sunshine')
                record=next(r for r in manifest if r['case_date']==case['date'] and r['day']==day)
                source=None;reason='missing_woudc';outputs={}
                try:
                    if record['status']=='downloaded':
                        series,_=read_woudc(OLD/'uv/woudc'/record['path']);source=observed_peak(series,valid)
                        reason=source['reason']
                        if reason=='usable':
                            base.update(observed_uvi=source['uvi'],observed_hourly_max=source['hourly'],observed_peak_start=str(source['peak_start']))
                            cams=load_cams(INPUT/'cams'/f'cams_{date-pd.Timedelta(days=1):%Y%m%d}_12.grib')
                            if pd.Timestamp(cams.attrs['forecast_reference_time']).tz_localize(None)!=date-pd.Timedelta(hours=12):raise ValueError('Wrong CAMS cycle')
                            observation=read_observations(INPUT/'observations'/f'{date:%Y%m%d}_day{day}.csv')
                            outputs,sw,obs=make_grid(date,day,site,raw,provenance,cams,table,observation)
                            base['sw_mean_error']=float(np.nanmean(sw-obs))
                            end=(pd.Timestamp(source['peak_start'])+pd.Timedelta(minutes=15)).floor('h')+pd.Timedelta(hours=1)
                            if ('DAV',end) in observation.index:
                                row=observation.loc[('DAV',end)]
                                if row.htoauths_quality==4:base['snow_regime']='Measured snow' if row.htoauths>0 else 'Snow-free' if row.htoauths==0 else 'Unknown snow'
                                if row.sre000h0_quality==4:base['sunshine_regime']=sunshine_regime(np.array([row.sre000h0]))[0]
                except (ValueError,KeyError,FileNotFoundError) as error:
                    reason='input_error';errors.append(dict(reference=case['reference'],day=day,error=str(error)))
                for product in PRODUCTS:
                    row=dict(base,product=product,reason=reason)
                    if reason=='usable':
                        if product not in outputs:row['reason']='unavailable_sw_substitution'
                        else:
                            result=daily_cells(outputs[product],valid,table)
                            if not result['available'][0]:row['reason']='incomplete_model_daylight'
                            else:row.update(predicted_uvi=result['uvi'][0],hourly_max=result['hourly_max_uvi'][0],quality_flag=int(result['quality_flag'][0]))
                    rows.append(row)
        print(case['date'],'processed',flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(OUTPUT/'daily_pairs.csv',index=False)
    (OUTPUT/'errors.json').write_text(json.dumps(errors,indent=2))
    summaries=[]
    for keys in [('day','product'),('day','product','season'),('day','product','snow_regime'),('day','product','configuration')]:
        for key,group in frame.groupby(list(keys)):
            good=group[group.reason=='usable'];row=dict(zip(keys,key));row.update(stratum='/'.join(keys),requested=len(group),usable=len(good),dates=good.valid_date.nunique())
            if len(good):row.update(product_scores(good.observed_uvi,good.predicted_uvi))
            summaries.append(row)
    pd.DataFrame(summaries).to_csv(OUTPUT/'scores.csv',index=False)
    frame.groupby(['day','product','reason']).size().rename('count').to_csv(OUTPUT/'coverage.csv')
    confidence=[]
    for (day,product),group in frame[frame.reason=='usable'].groupby(['day','product']):
        for block in (1,3,6):
            confidence.append(dict(day=int(day),product=product,block=block,dates=group.valid_date.nunique(),intervals=score_intervals(group,block=block)))
    (OUTPUT/'confidence.json').write_text(json.dumps(confidence,indent=2))
    comparisons=[]
    for day in (0,1):
        good=frame[(frame.day==day)&(frame.reason=='usable')]
        for left,right in [('native','gray'),('native','measured_sw'),('gray','measured_sw_gray')]:
            paired=good[good['product']==left].merge(good[good['product']==right],on=['valid_date','site','season'],suffixes=('_left','_right'))
            if not len(paired):continue
            delta=(abs(paired.predicted_uvi_left-paired.observed_uvi_left)-abs(paired.predicted_uvi_right-paired.observed_uvi_right)).to_numpy()
            for block in (1,3,6):
                boot=[float(delta[i].mean()) for i in date_block_indices(paired.valid_date,paired.season,block=block)]
                comparisons.append(dict(day=day,left=left,right=right,dates=paired.valid_date.nunique(),block=block,
                                        delta_mae_left_minus_right=float(delta.mean()),ci95=np.quantile(boot,[.025,.975]).tolist()))
    (OUTPUT/'paired_comparisons.json').write_text(json.dumps(comparisons,indent=2))
    print(pd.DataFrame(summaries).query("stratum == 'day/product'").to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze-only',action='store_true');args=parser.parse_args()
    freeze_inputs() if args.freeze_only else run()
