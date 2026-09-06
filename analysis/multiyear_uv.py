"""WOUDC-matched ICON POI diagnostics with explicit UV-albedo scenarios."""
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

from icon_uv.data import load_cams
from icon_uv.radiation import RadiationTable
from analysis.scientific import diagnose, metric, sunshine_regime, verify_inputs
from analysis.multiyear import INPUT, OUTPUT, read_observations, reconstructed_sw


def read_woudc(path):
    """Read one fixed instrument's extended CSV, retaining its metadata."""
    sections={}
    name=None
    for line in path.read_text().splitlines():
        if line.startswith('#'):
            name=line[1:].strip()
            if name in sections:raise ValueError('Duplicate WOUDC section')
            sections[name]=[]
        elif name and line.strip() and not line.startswith('*'):
            sections[name].append(line)
    metadata={}
    for section in ('CONTENT','DATA_GENERATION','INSTRUMENT','PLATFORM','LOCATION','TIMESTAMP'):
        records=list(csv.DictReader(sections[section]))
        if len(records)!=1:raise ValueError('Expected one WOUDC metadata record')
        metadata[section]=records[0]
    instrument=metadata['INSTRUMENT'];timestamp=metadata['TIMESTAMP'];location=metadata['LOCATION']
    if (instrument['Name'],instrument['Model'],instrument['Number'])!=('UV-Biometer','501A','1492'):
        raise ValueError('Wrong WOUDC instrument')
    if metadata['PLATFORM']['ID']!='501' or metadata['CONTENT']['Category']!='Broad-band':
        raise ValueError('Wrong WOUDC station/category')
    if metadata['DATA_GENERATION']['Agency']!='PMOD-WRC':raise ValueError('Wrong data agency')
    if timestamp['UTCOffset']!='+00:00:00':raise ValueError('Unqualified WOUDC time offset')
    coords=tuple(float(location[k]) for k in ('Latitude','Longitude','Height'))
    if not np.allclose(coords,(46.82,9.85,1590),rtol=0,atol=1e-5):
        raise ValueError('WOUDC location changed; remapping is required')
    values=pd.read_csv(io.StringIO('\n'.join(sections['GLOBAL'])))
    times=pd.to_datetime(timestamp['Date']+'T'+values.Time)
    if times.duplicated().any() or not times.is_monotonic_increasing:raise ValueError('Invalid WOUDC time order')
    return pd.Series(values.Irradiance.to_numpy(float)*40,index=times),metadata


def source_cadence(series):
    daylight=series.between_time('07:59','16:01')
    steps=np.diff(daylight.index.to_numpy()).astype('timedelta64[s]').astype(float)
    if len(steps)<10:raise ValueError('Insufficient samples to establish cadence')
    nominal=float(np.median(steps))
    if 8<=nominal<=12:return nominal,30
    if 55<=nominal<=65:return nominal,75
    raise ValueError(f'Unqualified UV sampling cadence: {nominal} seconds')


def integrate_hour(series,start,max_gap_seconds=30):
    """Hourly mean from linearly connected samples, with strict gap coverage."""
    end=start+pd.Timedelta(hours=1)
    seconds=(series.index-start).total_seconds().to_numpy()
    left=np.searchsorted(seconds,0,side='right')-1
    right=np.searchsorted(seconds,3600,side='left')
    if left<0 or right>=len(seconds):return np.nan,'no_boundary_bracket',0
    x=seconds[left:right+1];y=series.iloc[left:right+1].to_numpy(float)
    if np.any(np.diff(x)>max_gap_seconds):return np.nan,'gap_exceeds_cadence_limit',len(x)
    if not np.isfinite(y).all() or (y<0).any():return np.nan,'invalid_sample',len(x)
    inside=(x>0)&(x<3600)
    knots=np.r_[0,x[inside],3600]
    vals=np.interp(knots,x,y)
    return float(np.trapezoid(vals,knots)/3600),'usable',len(x)


def summarize_uv(frame,groups):
    rows=[]
    for key,group in frame.groupby(groups,dropna=False):
        key=key if isinstance(key,tuple) else (key,)
        for product in ('reference_uvi','gray_uvi','bright_uvi','snow_uvi'):
            good=group[(group.reason=='usable')&np.isfinite(group[product])]
            row=dict(zip(groups,key));row.update(product=product,requested=len(group),usable=len(good),
                initializations=good.reference.nunique(),dates=good.valid_date.nunique())
            if len(good):
                row.update(metric(good.observed_uvi.to_numpy(),good[product].to_numpy()))
                daily=good.assign(error=good[product]-good.observed_uvi).groupby('valid_date').error
                row['equal_day_bias']=daily.mean().mean()
                row['equal_day_mae']=daily.apply(lambda x:x.abs().mean()).mean()
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    verify_inputs(INPUT,INPUT/'frozen_inputs.json')
    verify_inputs(INPUT/'uv',INPUT/'uv/frozen_inputs.json')
    frozen=json.loads((INPUT/'uv/frozen_inputs.json').read_text())
    from analysis.multiyear import ROOT
    for field,path in [('protocol_sha256',ROOT/'analysis/MULTIYEAR_UV_PLAN.md'),('table_sha256',ROOT/'icon_uv/data/rt.npz')]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=frozen[field]:raise ValueError(f'Changed {field}')
    cfg=json.loads((INPUT/'campaign.json').read_text());site=cfg['uv_stations'][0];col=len(cfg['stations'])
    raw_manifest=json.loads((INPUT/'uv/woudc_manifest.json').read_text())['inputs']
    table=RadiationTable();rows=[];coverage=[];file_metadata=[]
    for case in cfg['cases']:
        date=pd.Timestamp(case['reference']).tz_localize(None)
        record_map={r['day']:r for r in raw_manifest if r['case_date']==case['date']}
        for day in (0,1):
            starts=pd.date_range(date+pd.Timedelta(days=day,hours=8),periods=8,freq='h')
            base=[dict(reference=case['reference'],case_date=case['date'],day=day,time=t+pd.Timedelta(minutes=30),
                       valid_date=str(t.date()),year=t.year,season={12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'}[t.month],observed_uvi=np.nan,
                       reference_uvi=np.nan,gray_uvi=np.nan,bright_uvi=np.nan,snow_uvi=np.nan,
                       sunshine=np.nan,snow_cm=np.nan,reason='missing_woudc') for t in starts]
            source=record_map[day]
            if source['status']!='downloaded':rows.extend(base);continue
            try:
                series,metadata=read_woudc(INPUT/'uv/woudc'/source['path'])
                if metadata['TIMESTAMP']['Date']!=str(starts[0].date()):raise ValueError('Wrong WOUDC date')
                nominal,max_gap=source_cadence(series)
                file_metadata.append(dict(path=source['path'],nominal_seconds=nominal,max_gap_seconds=max_gap,**metadata))
                for row,start in zip(base,starts):
                    value,reason,count=integrate_hour(series,start,max_gap_seconds=max_gap)
                    row.update(observed_uvi=value,reason=reason,uv_samples=count,nominal_seconds=nominal,max_gap_seconds=max_gap)
                path=INPUT/'icon'/f'{date:%Y%m%d}_00.npz'
                provenance=json.loads(path.with_suffix('.json').read_text())
                if provenance['reference']!=case['reference'] or provenance['member']!=0:raise ValueError('ICON identity mismatch')
                with np.load(path) as raw:
                    if raw['cell'][col]!=site['cell']:raise ValueError('Wrong UV source cell')
                    leads=list(range(8+24*day,17+24*day));indices=[list(raw['leads']).index(h) for h in leads]
                    sw=reconstructed_sw(raw,provenance['records'],leads)[:,col]
                    pressure=((raw['pressure'][indices[:-1],col]+raw['pressure'][indices[1:],col])/2
                              *np.exp(-(site['altitude_m']-raw['height'][col])/8434))
                    albedo=(raw['albedo'][indices[:-1],col]+raw['albedo'][indices[1:],col])/200
                cams=load_cams(INPUT/'uv'/f"cams_{date-pd.Timedelta(days=1):%Y%m%d}_12.grib")
                expected=pd.Timestamp(date-pd.Timedelta(hours=12))
                if pd.Timestamp(cams.attrs['forecast_reference_time']).tz_localize(None)!=expected:raise ValueError('CAMS cycle mismatch')
                coords=(cams.time.values.astype('datetime64[s]').astype(float),cams.latitude.values,cams.longitude.values)
                midpoint=(starts+pd.Timedelta(minutes=30)).to_numpy()
                target=np.column_stack([midpoint.astype('datetime64[s]').astype(float),np.full(8,site['latitude']),np.full(8,site['longitude'])])
                ozone,aod=[RegularGridInterpolator(coords,cams[name].values,bounds_error=True)(target) for name in ('ozone_du','aod550')]
                obs=read_observations(INPUT/'observations'/f'{date:%Y%m%d}_day{day}.csv')
                valid=(np.isfinite(sw+pressure+albedo+ozone+aod)&(sw>=0)&(pressure>=50000)&(pressure<=105000)
                       &(albedo>=0)&(albedo<=.85)&(ozone>=200)&(ozone<=500)&(aod>=0)&(aod<=1))
                result={}
                if valid.any():
                    for label,uv_albedo in [('reference',.05),('bright',.15),('snow',.80)]:
                        result[label]=diagnose(midpoint[valid],site['latitude'],site['longitude'],ozone[valid],aod[valid],
                                              pressure[valid],sw[valid],albedo[valid],uv_albedo,table=table)
                position=0
                for i,row in enumerate(base):
                    row.update(model_sw=float(sw[i]),pressure_pa=float(pressure[i]),sw_albedo=float(albedo[i]),
                               ozone_du=float(ozone[i]),aod550=float(aod[i]),configuration=provenance['configuration'])
                    key=('DAV',starts[i]+pd.Timedelta(hours=1))
                    if key in obs.index:
                        observation=obs.loc[key]
                        if observation.sre000h0_quality==4:row['sunshine']=observation.sre000h0
                        if observation.htoauths_quality==4:row['snow_cm']=observation.htoauths
                    if not valid[i]:row['reason']='driver_out_of_table';continue
                    for label in result:row[label+'_uvi']=float(result[label]['uvi'][position])
                    for name in ('gray_uvi','clear_uvi','clear_sw','tau','flag','mean_sza'):
                        row[name]=float(result['reference'][name][position])
                    position+=1
            except (ValueError,FileNotFoundError,KeyError) as error:
                for row in base:
                    if row['reason']=='usable':row['reason']='driver_unavailable'
                coverage.append(dict(case_date=case['date'],day=day,error=str(error)))
            rows.extend(base)
    frame=pd.DataFrame(rows)
    frame['sunshine_regime']=sunshine_regime(frame.sunshine)
    frame['snow_regime']=np.select([frame.snow_cm==0,frame.snow_cm>0],['Snow-free','Measured snow'],default='Unknown snow')
    frame.to_csv(OUTPUT/'uv_pairs.csv',index=False)
    for name,groups in [('overall',['day']),('season',['day','season']),('snow',['day','snow_regime']),
                        ('sunshine',['day','sunshine_regime']),('daily',['day','valid_date'])]:
        summarize_uv(frame,groups).to_csv(OUTPUT/f'uv_{name}.csv',index=False)
    frame.groupby(['day','reason']).size().rename('count').to_csv(OUTPUT/'uv_exclusions.csv')
    (OUTPUT/'uv_errors.json').write_text(json.dumps(coverage,indent=2))
    (OUTPUT/'woudc_metadata.json').write_text(json.dumps(file_metadata,indent=2))
    print(pd.read_csv(OUTPUT/'uv_overall.csv').to_string(index=False))


if __name__=='__main__':main()
