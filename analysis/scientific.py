"""Reproducible scientific evaluation with frozen inputs and explicit cohorts.

No retrieval, fitting, gap filling or forecast mutation occurs in this module.
Run: python -m analysis.scientific
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version

import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree

from icon_uv.data import load_cams
from icon_uv.products import _xyz, compute_grid
from icon_uv.radiation import RadiationTable, solar_geometry

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'work/scientific-hardening-20260906'
OLD=ROOT/'work/scientific-validation-20260906'
OUTPUT=INPUT/'results'
PRIMARY_HOURS=(8,16)


def verify_inputs(root=ROOT, manifest_path=INPUT/'frozen_inputs.json'):
    manifest=json.loads(manifest_path.read_text())
    for item in manifest['inputs']:
        path=root/item['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError(f"Frozen input changed or missing: {item['path']}")
    return manifest


def metric(observed, predicted):
    observed,predicted=np.asarray(observed,float),np.asarray(predicted,float)
    if observed.shape!=predicted.shape or observed.ndim!=1:
        raise ValueError('Metric requires equal one-dimensional paired arrays')
    if not np.isfinite(observed).all() or not np.isfinite(predicted).all():
        raise ValueError('Select and disclose finite pairs before scoring')
    if not len(observed): return {'n':0}
    error=predicted-observed
    return dict(n=len(error),bias=error.mean(),mae=np.abs(error).mean(),
                rmse=np.sqrt(np.mean(error**2)),median_error=np.median(error),
                observed_mean=observed.mean(),predicted_mean=predicted.mean(),
                relative_mean_excess=predicted.sum()/observed.sum()-1 if observed.sum()>0 else np.nan)


def matched_uv_dose_error(observed, predicted, interval_hours):
    """Signed erythemal radiant-exposure error over the supplied matched intervals."""
    metric(observed,predicted)  # Equal finite arrays are mandatory, including zeros.
    hours=np.asarray(interval_hours,float)
    if hours.shape!=np.asarray(observed).shape or not np.isfinite(hours).all() or np.any(hours<=0):
        raise ValueError('Dose requires positive finite duration for every pair')
    return float(90*np.sum((np.asarray(predicted)-np.asarray(observed))*hours))


def sunshine_regime(minutes):
    minutes=np.asarray(minutes,float)
    valid=np.isfinite(minutes)&(minutes>=0)&(minutes<=60)
    return np.select([valid&(minutes<=5),valid&(minutes>=50),valid&(minutes>5)&(minutes<50)],
                     ['0–5 min sunshine','50–60 min sunshine','Intermediate sunshine'],default='Unknown sunshine')


def uv_series(raw, site):
    values=raw.get(site,{}).get('uve')
    if values is None: return pd.Series(dtype=float,index=pd.DatetimeIndex([]))
    if values.get('unit')!='UV-Index': raise ValueError('UV unit must be UV-Index')
    times,measurements=values['ts'],values['measurement']
    if len(times)!=len(measurements): raise ValueError('UV timestamp/value length mismatch')
    if any(datetime.fromisoformat(t.replace('Z','+00:00')).tzinfo is None for t in times):
        raise ValueError('UV timestamps must state their UTC offset')
    index=pd.to_datetime(times,utc=True).tz_localize(None)
    if index.duplicated().any(): raise ValueError('Duplicate UV timestamp')
    return pd.Series(measurements,index=index,dtype=float).sort_index()


def hourly_uv(series, starts):
    rows=[]
    for start in pd.to_datetime(starts):
        wanted=pd.DatetimeIndex([start+pd.Timedelta(minutes=15),start+pd.Timedelta(minutes=45)])
        values=series.reindex(wanted).to_numpy(float)
        complete=bool(wanted.isin(series.index).all())
        reason='missing_timestamp' if not complete else 'nonfinite' if not np.isfinite(values).all() else 'negative' if (values<0).any() else 'usable'
        rows.append(dict(time=start+pd.Timedelta(minutes=30),uv_reason=reason,
                         observed_uvi=values.mean() if reason=='usable' else np.nan,
                         uv_first=values[0],uv_second=values[1],uv_qc='unconfirmed',
                         uv_temporal_support='mean of :15/:45 reported values; averaging metadata unconfirmed'))
    return pd.DataFrame(rows)


def matched_cycle_errors(base, newer, keys=('site','time')):
    for frame in [base,newer]:
        if frame.duplicated(list(keys)).any(): raise ValueError('Duplicate cycle comparison key')
    columns=[*keys,'observed_uvi','forecast_uvi']
    joined=base[columns].merge(newer[columns],on=list(keys),how='inner',validate='one_to_one',suffixes=('_base','_new'))
    if not np.allclose(joined.observed_uvi_base,joined.observed_uvi_new,rtol=0,atol=0):
        raise ValueError('Paired cycles must use identical observations')
    if not np.isfinite(joined.select_dtypes('number')).all().all(): raise ValueError('Nonfinite paired cycle values')
    joined['base_absolute_error']=abs(joined.forecast_uvi_base-joined.observed_uvi_base)
    joined['new_absolute_error']=abs(joined.forecast_uvi_new-joined.observed_uvi_base)
    joined['delta_absolute_error']=joined.new_absolute_error-joined.base_absolute_error
    return joined


def nearest_cells(grid, sites):
    tree=cKDTree(_xyz(grid.latitude.values,grid.longitude.values));rows=[]
    for site in sites:
        chord,index=tree.query(_xyz(site['latitude'],site['longitude']))
        index=int(np.asarray(index).item()); distance=2*6371*np.arcsin(min(float(np.asarray(chord).item())/2,1))
        rows.append(dict(site=unquote(site['name']),api_site=site['name'],cell_index=index,
                         cell_id=int(grid.cell[index]),distance_km=distance,
                         site_altitude=site['altitude'],model_altitude=float(grid.altitude_m[index]),
                         latitude=site['latitude'],longitude=site['longitude'],country=site['country'],
                         in_domain=distance<=10))
    return pd.DataFrame(rows)


def diagnose(time, lat, lon, ozone, aod, pressure, sw, sw_albedo, uv_albedo, *, samples=4, table=None):
    """Evaluate independent intervals as columns; never tune to UV measurements."""
    table=RadiationTable() if table is None else table
    time=np.asarray(time,dtype='datetime64[ns]')
    offsets=((np.arange(samples)+.5)/samples*3600-1800)*1e9
    sample_time=time[None,:]+offsets.astype('timedelta64[ns]')[:,None]
    lat,lon,ozone,aod,pressure,sw,sw_albedo,uv_albedo=np.broadcast_arrays(lat,lon,ozone,aod,pressure,sw,sw_albedo,uv_albedo)
    z,_,distance=solar_geometry(sample_time,lat,lon)
    tau,scale,flag=table.cloud(z,distance,ozone,pressure,aod,sw_albedo,sw)
    flux=table.at(z,ozone,pressure,aod,uv_albedo,tau)
    uv=40*(flux[...,2:].sum(axis=-1)*distance*scale).mean(axis=0)
    clear_uv=40*(table.at(z,ozone,pressure,aod,uv_albedo,0)[...,2:].sum(axis=-1)*distance).mean(axis=0)
    clear_sw=(table.at(z,ozone,pressure,aod,sw_albedo,0)[...,:2].sum(axis=-1)*distance).mean(axis=0)
    # Deliberately allow ratios >1 and preserve flags rather than hide enhancement.
    gray=np.divide(clear_uv*sw,clear_sw,out=np.zeros_like(clear_uv),where=clear_sw>0)
    return dict(uvi=uv,gray_uvi=gray,clear_uvi=clear_uv,clear_sw=clear_sw,tau=tau,flag=flag,
                mean_sza=z.mean(axis=0))


def load_smn(code):
    paths=[INPUT/f'ogd-smn_{code.lower()}_h_recent.csv',OLD/f'ogd-smn_{code.lower()}_h_now.csv']
    frames=[]
    for path in paths:
        if not path.exists(): continue
        frame=pd.read_csv(path,sep=';')
        if frame.station_abbr.nunique()!=1 or frame.station_abbr.iloc[0]!=code:
            raise ValueError('Unexpected SwissMetNet station identity')
        frame['end']=pd.to_datetime(frame.reference_timestamp,format='%d.%m.%Y %H:%M')
        if frame.end.duplicated().any(): raise ValueError('Duplicate SwissMetNet timestamp')
        frames.append(frame.set_index('end'))
    # Overlaps must agree; never silently choose a source revision.
    combined=pd.concat(frames)
    for _,group in combined[combined.index.duplicated(keep=False)].groupby(level=0):
        for variable in ['gre000h0','prestah0','sre000h0']:
            values=group[variable].to_numpy(float)
            if not np.allclose(values,values[0],equal_nan=True): raise ValueError('Conflicting SwissMetNet source revisions')
    return combined[~combined.index.duplicated()].sort_index()


def summarize(frame, groups, predicted, observed='observed_uvi'):
    rows=[]
    for key,subset in frame.groupby(groups,dropna=False,sort=True):
        key=(key,) if not isinstance(key,tuple) else key
        for product in predicted:
            valid=np.isfinite(subset[observed])&np.isfinite(subset[product])
            rows.append(dict(zip(groups,key),product=product,eligible_rows=len(subset),
                             excluded_nonfinite=int((~valid).sum()),**metric(subset.loc[valid,observed],subset.loc[valid,product])))
    return pd.DataFrame(rows)


def forecast_analysis(raw, sites):
    composition=load_cams(INPUT/'cams_20260904_12.grib')
    table=RadiationTable(); all_rows=[]; regional=[]
    station_meta=pd.read_csv(OLD/'ogd-smn_meta_stations.csv',sep=';',encoding='cp1252').set_index('station_abbr')
    for cycle in ['00','06','12']:
        with xr.open_dataset(INPUT/f'icon_20260905_{cycle}.nc') as source: icon=source.load()
        links=nearest_cells(icon,sites)
        if cycle=='00': links.to_csv(OUTPUT/'site_mapping.csv',index=False)
        selected=links[links.in_domain]
        at_sites=icon.isel(cell=selected.cell_index.to_numpy())
        forecast=compute_grid(at_sites,composition,table)
        refined=compute_grid(at_sites,composition,table,samples=12)
        forecast.to_netcdf(OUTPUT/f'uv_sites_{cycle}.nc',encoding={v:{'units':'hours since 2026-09-05 00:00:00','calendar':'proleptic_gregorian'} for v in ['time','time_bounds']})
        for j,link in enumerate(selected.itertuples()):
            data=forecast.isel(cell=j)
            paired=hourly_uv(uv_series(raw,link.api_site),data.time_bounds.values[:,0])
            paired['site']=link.site;paired['cycle']=cycle
            paired['lead_hours']=(paired.time-pd.Timestamp(f'2026-09-05 {cycle}:00:00')).dt.total_seconds()/3600
            for target,field in [('forecast_uvi','uvi'),('clear_uvi','clear_sky_uvi'),('model_sw','sw_down'),('model_flag','quality_flag'),('ozone','ozone_du'),('aod','aod550'),('snow_fraction','snow_fraction')]:
                # Promote saved float32 forecasts before CSV serialization so the
                # archived decimal pairs retain the exact values used in scores.
                paired[target]=data[field].values.astype(int if target=='model_flag' else float)
            d=diagnose(data.time.values,np.full(len(paired),float(data.latitude)),np.full(len(paired),float(data.longitude)),data.ozone_du.values,data.aod550.values,data.pressure_pa.values,data.sw_down.values,data.sw_albedo.values,data.uv_albedo.values,table=table)
            if not np.allclose(d['uvi'],paired.forecast_uvi,rtol=0,atol=3e-6): raise ValueError('Site reconstruction mismatch')
            paired['gray_forecast_uvi']=d['gray_uvi'];paired['distance_km']=link.distance_km
            paired['mean_sza']=d['mean_sza'];paired['uvi_12_samples']=refined.uvi.values[:,j].astype(float)
            paired['quadrature_delta']=paired.uvi_12_samples-paired.forecast_uvi
            all_rows.append(paired)
        tree=cKDTree(_xyz(icon.latitude.values,icon.longitude.values))
        for file in sorted(OLD.glob('ogd-smn_*_h_now.csv')):
            obs=pd.read_csv(file,sep=';'); code=obs.station_abbr.iloc[0]
            if code not in station_meta.index: continue
            station=station_meta.loc[code]
            distance,index=tree.query(_xyz(station.station_coordinates_wgs84_lat,station.station_coordinates_wgs84_lon))
            distance=2*6371*np.arcsin(min(float(np.asarray(distance).item())/2,1))
            if distance>10: continue
            obs['end']=pd.to_datetime(obs.reference_timestamp,format='%d.%m.%Y %H:%M')
            if obs.end.duplicated().any(): raise ValueError('Duplicate regional SW timestamp')
            obs=obs.set_index('end'); local=icon.isel(cell=int(np.asarray(index).item()))
            for i,mid in enumerate(icon.time.values):
                end=pd.Timestamp(icon.time_bounds.values[i,1])
                if end not in obs.index or not np.isfinite(obs.loc[end,'gre000h0']): continue
                value=float(obs.loc[end,'gre000h0'])
                if value<0: continue
                regional.append(dict(cycle=cycle,station=code,time=pd.Timestamp(mid),observed_sw=value,
                                     predicted_sw=float(local.sw_down[i]),sunshine=float(obs.loc[end,'sre000h0']),
                                     altitude=station.station_height_masl,distance_km=distance))
    pairs=pd.concat(all_rows,ignore_index=True)
    pairs['hour']=pairs.time.dt.hour+.5
    pairs.to_csv(OUTPUT/'forecast_pairs.csv',index=False)
    coverage=pairs.groupby(['cycle','site','uv_reason']).size().rename('hours').reset_index()
    # Include sites absent from the API via their explicit missing_timestamp rows.
    coverage.to_csv(OUTPUT/'forecast_coverage.csv',index=False)
    primary=pairs[(pairs.hour>=8)&(pairs.hour<16)]
    summarize(primary,['cycle','site'],['forecast_uvi','gray_forecast_uvi']).to_csv(OUTPUT/'forecast_primary.csv',index=False)
    secondary=pairs[pairs.observed_uvi>=1]
    summarize(secondary,['cycle','site'],['forecast_uvi']).to_csv(OUTPUT/'forecast_secondary.csv',index=False)
    matched=[]
    for newer in ['06','12']:
        valid=primary[primary.uv_reason=='usable']
        joint=matched_cycle_errors(valid[valid.cycle=='00'],valid[valid.cycle==newer])
        joint['comparison']='00_vs_'+newer; matched.append(joint)
    paired=pd.concat(matched,ignore_index=True);paired.to_csv(OUTPUT/'paired_cycle_errors.csv',index=False)
    paired.groupby(['comparison','site']).agg(n=('time','size'),base_mae=('base_absolute_error','mean'),new_mae=('new_absolute_error','mean'),delta_mae=('delta_absolute_error','mean')).reset_index().to_csv(OUTPUT/'paired_cycle_summary.csv',index=False)
    pd.DataFrame(regional).to_csv(OUTPUT/'regional_pairs.csv',index=False)
    regional=pd.DataFrame(regional);regional['hour']=regional.time.dt.hour+.5
    regional=regional[(regional.hour>=8)&(regional.hour<16)]
    regional['sunshine_regime']=sunshine_regime(regional.sunshine)
    summarize(regional,['cycle','sunshine_regime'],['predicted_sw'],'observed_sw').to_csv(OUTPUT/'regional_regimes.csv',index=False)
    summarize(regional,['cycle'],['predicted_sw'],'observed_sw').to_csv(OUTPUT/'regional_summary.csv',index=False)
    sw_matched=[]
    adapted=regional.rename(columns={'station':'site','observed_sw':'observed_uvi','predicted_sw':'forecast_uvi'})
    for newer in ['06','12']:
        joint=matched_cycle_errors(adapted[adapted.cycle=='00'],adapted[adapted.cycle==newer])
        joint['comparison']='00_vs_'+newer; sw_matched.append(joint)
    sw_matched=pd.concat(sw_matched,ignore_index=True)
    sw_matched.rename(columns={'observed_uvi_base':'observed_sw_base','observed_uvi_new':'observed_sw_new',
                              'forecast_uvi_base':'predicted_sw_base','forecast_uvi_new':'predicted_sw_new','site':'station'}).to_csv(OUTPUT/'regional_paired_errors.csv',index=False)
    sw_matched.groupby('comparison').agg(n=('time','size'),stations=('site','nunique'),
        base_mae_wm2=('base_absolute_error','mean'),new_mae_wm2=('new_absolute_error','mean'),
        delta_mae_wm2=('delta_absolute_error','mean')).reset_index().to_csv(OUTPUT/'regional_paired_summary.csv',index=False)
    return pairs


def historical_analysis(raw, sites):
    table=RadiationTable(); meta=pd.read_csv(OLD/'ogd-smn_meta_stations.csv',sep=';',encoding='cp1252').set_index('station_abbr')
    rows=[]
    for site_name,code in [('Davos','DAV'),('Weissfluhjoch','WFJ')]:
        site=next(s for s in sites if s['name']==site_name)
        source=load_smn(code); obs=uv_series(raw,site_name)
        for day in pd.date_range('2026-08-29','2026-09-05'):
            starts=pd.date_range(day+pd.Timedelta(hours=4),day+pd.Timedelta(hours=17),freq='h')
            frame=hourly_uv(obs,starts)
            frame['site']=site_name;frame['date']=day.strftime('%Y-%m-%d')
            measured=source.reindex(starts+pd.Timedelta(hours=1))
            frame['measured_sw']=measured.gre000h0.to_numpy(float)
            frame['station_pressure_pa']=measured.prestah0.to_numpy(float)*100
            frame['sunshine_minutes']=measured.sre000h0.to_numpy(float)
            frame['pressure_pa']=frame.station_pressure_pa*np.exp(-(site['altitude']-float(meta.loc[code,'station_height_barometer_masl']))/8434)
            cams=load_cams(INPUT/f"cams_{(day-pd.Timedelta(days=1)).strftime('%Y%m%d')}_12.grib")
            coords=(cams.time.values.astype('datetime64[s]').astype(float),cams.latitude.values,cams.longitude.values)
            target=np.column_stack([frame.time.to_numpy().astype('datetime64[s]').astype(float),np.full(len(frame),site['latitude']),np.full(len(frame),site['longitude'])])
            for name in ['ozone_du','aod550']:
                frame[name]=RegularGridInterpolator(coords,cams[name].values,bounds_error=True)(target)
            valid=np.isfinite(frame[['measured_sw','pressure_pa','ozone_du','aod550']]).all(axis=1)&(frame.measured_sw>=0)
            frame['driver_usable']=valid
            for label,sw_albedo,uv_albedo in [('reference',.15,.05),('dark',.05,0),('bright_soil',.30,.15),('snow',.60,.80)]:
                subset=frame.loc[valid]
                diagnosis=diagnose(subset.time.to_numpy(),np.full(len(subset),site['latitude']),np.full(len(subset),site['longitude']),subset.ozone_du.to_numpy(),subset.aod550.to_numpy(),subset.pressure_pa.to_numpy(),subset.measured_sw.to_numpy(),np.full(len(subset),sw_albedo),np.full(len(subset),uv_albedo),table=table)
                frame.loc[valid,label+'_uvi']=diagnosis['uvi']
                if label=='reference':
                    for field in ['gray_uvi','clear_uvi','clear_sw','tau','flag','mean_sza']: frame.loc[valid,field]=diagnosis[field]
            rows.append(frame)
    all_pairs=pd.concat(rows,ignore_index=True);all_pairs['hour']=all_pairs.time.dt.hour+.5
    all_pairs['sunshine_regime']=sunshine_regime(all_pairs.sunshine_minutes)
    all_pairs['observation_age_group']=np.where(all_pairs.date<='2026-09-01','at least 5 days old','less than 5 days old')
    all_pairs.to_csv(OUTPUT/'historical_pairs.csv',index=False)
    primary=all_pairs[(all_pairs.hour>=8)&(all_pairs.hour<16)]
    products=['reference_uvi','gray_uvi','dark_uvi','bright_soil_uvi','snow_uvi']
    daily=summarize(primary,['site','date'],products)
    daily['matched_window_dose_error_jm2']=daily.bias*daily.n*90
    daily.to_csv(OUTPUT/'historical_daily.csv',index=False)
    summarize(primary,['site'],products).to_csv(OUTPUT/'historical_summary.csv',index=False)
    summarize(primary,['site','sunshine_regime'],['reference_uvi','gray_uvi']).to_csv(OUTPUT/'historical_regimes.csv',index=False)
    summarize(primary,['site','observation_age_group'],['reference_uvi','gray_uvi']).to_csv(OUTPUT/'historical_age_groups.csv',index=False)
    usable=primary[np.isfinite(primary.observed_uvi)&np.isfinite(primary.reference_uvi)]
    usable.groupby(['site','flag']).size().rename('n').reset_index().to_csv(OUTPUT/'historical_flags.csv',index=False)
    # The ratio is a diagnostic and does not independently label a clear sky.
    usable.assign(sw_to_modeled_clear=usable.measured_sw/usable.clear_sw).groupby('site').agg(
        n=('time','size'),maximum_sw_to_clear=('sw_to_modeled_clear','max'),
        median_sw_to_clear=('sw_to_modeled_clear','median')).reset_index().to_csv(OUTPUT/'historical_transmission.csv',index=False)
    loo=[]
    for site,group in primary.groupby('site'):
        usable=group[np.isfinite(group.observed_uvi)&np.isfinite(group.reference_uvi)]
        for omitted in sorted(usable.date.unique()):
            valid=group[(group.date!=omitted)&np.isfinite(group.observed_uvi)&np.isfinite(group.reference_uvi)]
            loo.append(dict(site=site,omitted_date=omitted,**metric(valid.observed_uvi,valid.reference_uvi)))
    pd.DataFrame(loo).to_csv(OUTPUT/'leave_one_day_out.csv',index=False)
    daily[(daily['product']=='reference_uvi')&(daily.n>0)].groupby('site').agg(
        days_with_data=('date','size'),complete_days=('n',lambda x:int((x==8).sum())),
        equal_day_mean_bias=('bias','mean'),minimum_daily_bias=('bias','min'),maximum_daily_bias=('bias','max')
    ).reset_index().to_csv(OUTPUT/'historical_day_distribution.csv',index=False)
    return all_pairs


def run():
    manifest=verify_inputs(); OUTPUT.mkdir(parents=True,exist_ok=True)
    raw=json.loads((INPUT/'uv_8days.json').read_text());sites=json.loads((INPUT/'uv_sites.json').read_text())
    forecast=forecast_analysis(raw,sites)
    historical=historical_analysis(raw,sites)
    original=json.loads((OLD/'uv-observations-fresh.json').read_text());revisions=[]
    for site in ['Davos','Weissfluhjoch','Zugspitze','Aosta']:
        before=uv_series(original,site); after=uv_series(raw,site).reindex(before.index)
        revisions.append(dict(site=site,previous_values=len(before),matched_values=int(after.notna().sum()),changed_values=int((abs(after-before)>1e-12).sum())))
    pd.DataFrame(revisions).to_csv(OUTPUT/'uv_revisions.csv',index=False)
    identity={'input_manifest_sha256':hashlib.sha256((INPUT/'frozen_inputs.json').read_bytes()).hexdigest(),
              'input_count':len(manifest['inputs']),'python':platform.python_version(),
              'packages':{p:version(p) for p in ['icon-uv','numpy','scipy','pandas','xarray','eccodes']},
              'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'analysis').glob('*.py')),ROOT/'analysis/SCIENTIFIC_PLAN.md',*sorted((ROOT/'icon_uv').glob('*.py'))]},
              'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'tracked_diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff','--binary'],cwd=ROOT)).hexdigest(),
              'forecast_rows':len(forecast),'historical_rows':len(historical),
              'evaluation_type':'Forecast cycles and separate observation-driven historical conversion; no fitting'}
    (OUTPUT/'run_identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    print(pd.read_csv(OUTPUT/'historical_summary.csv').to_string(index=False))
    print(pd.read_csv(OUTPUT/'regional_summary.csv').to_string(index=False))
    return forecast,historical


if __name__=='__main__': run()
