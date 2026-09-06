"""Score the frozen native ICON SW campaign; no full-UV validation claim."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from icon_uv.data import interval_radiation
from analysis.scientific import metric, sunshine_regime, verify_inputs

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'work/scientific-multiyear-20260906'
OUTPUT = INPUT / 'results'


def freeze_inputs(directory=INPUT):
    manifest = directory / 'frozen_inputs.json'
    if manifest.exists():
        return verify_inputs(directory, manifest)
    paths = [directory/'campaign.json']
    paths += sorted((directory/'icon').glob('*.npz'))
    paths += sorted((directory/'icon').glob('*.json'))
    paths += sorted((directory/'observations').glob('*.csv'))
    paths += sorted((directory/'observations').glob('*.json'))
    document = dict(created=datetime.now(timezone.utc).isoformat(), inputs=[
        dict(path=str(p.relative_to(directory)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])
    manifest.write_text(json.dumps(document, indent=2))
    verify_inputs(directory, manifest)


def read_observations(path):
    """DWH repeats 'dq' after each parameter; bind each flag to its predecessor."""
    with path.open() as stream:
        header = stream.readline().strip().split(';')
    names = []
    for index, name in enumerate(header):
        names.append(header[index-1]+'_quality' if name == 'dq' else name)
    if len(names) != len(set(names)):
        raise ValueError('Duplicate observation columns')
    data = pd.read_csv(path, sep=';', names=names, skiprows=1, dtype={'station': str})
    if data.astype(str).apply(lambda x: x.str.contains('# ERROR', regex=False)).any().any():
        raise ValueError('DWH returned an error')
    data['valid_end'] = pd.to_datetime(data.termin.astype(str), format='%Y%m%d%H%M%S')
    if data.duplicated(['nat_abbr', 'valid_end']).any():
        raise ValueError('Duplicate station-hour observations')
    for field in ['gre000h0','sre000h0','prestah0','htoauths','rre150h0']:
        for name in [field, field+'_quality']:
            if name not in data:
                data[name] = np.nan
    return data.set_index(['nat_abbr','valid_end'])


def reconstructed_sw(raw, records, leads):
    index = [list(raw['leads']).index(lead) for lead in leads]
    errors = [sum(r['packingError'] for r in records
                  if r['field'] in ('direct','diffuse') and r['endStep']==lead) for lead in leads]
    for lead in leads:
        if sum(r['field'] in ('direct','diffuse') and r['endStep']==lead for r in records) != 2:
            raise ValueError('Missing or duplicate radiation provenance')
    return interval_radiation(leads, raw['direct'][index]+raw['diffuse'][index], errors)


def case_rows(case, cfg, directory=INPUT):
    stamp = pd.Timestamp(case['reference']).tz_localize(None)
    stem = stamp.strftime('%Y%m%d_00')
    meta = json.loads((directory/'icon'/f'{stem}.json').read_text())
    if meta['reference'] != case['reference'] or meta['member'] != 0 or meta['grid_uuid'] != cfg['grid_uuid']:
        raise ValueError('Case identity does not match manifest')
    rawpath=directory/'icon'/f'{stem}.npz'
    if hashlib.sha256(rawpath.read_bytes()).hexdigest() != meta['output_sha256']:
        raise ValueError('Extracted boundary data changed')
    rows=[]
    with np.load(rawpath) as raw:
        if list(raw['cell'][:len(cfg['stations'])]) != [s['cell'] for s in cfg['stations']]:
            raise ValueError('Cell order differs from campaign')
        for day in (0,1):
            leads=list(range(8+24*day,17+24*day))
            sw=reconstructed_sw(raw,meta['records'],leads)
            observations=read_observations(directory/'observations'/f'{stamp:%Y%m%d}_day{day}.csv')
            for hour,lead in enumerate(leads[:-1]):
                end=stamp+pd.Timedelta(hours=lead+1)
                for col,site in enumerate(cfg['stations']):
                    key=(site['station'],end)
                    obs=observations.loc[key] if key in observations.index else pd.Series(dtype=float)
                    measured=float(obs.get('gre000h0',np.nan))
                    quality=float(obs.get('gre000h0_quality',np.nan))
                    sun=float(obs.get('sre000h0',np.nan)) if obs.get('sre000h0_quality')==4 else np.nan
                    snow=float(obs.get('htoauths',np.nan)) if obs.get('htoauths_quality')==4 else np.nan
                    lat=float(obs.get('latitude',np.nan));lon=float(obs.get('longitude',np.nan))
                    location_change=(np.isfinite(lat) and np.isfinite(lon) and
                        (abs(lat-site['latitude'])>1e-4 or abs(lon-site['longitude'])>1e-4))
                    reason=('missing_observation' if not np.isfinite(measured) else
                            'observation_quality' if quality!=4 else
                            'negative_observation' if measured<0 else
                            'station_position_changed' if location_change else 'usable')
                    boundary_index=list(raw['leads']).index(lead)
                    model_snow=(raw['snow_depth'][boundary_index,col]+raw['snow_depth'][boundary_index+1,col])/2
                    rows.append(dict(reference=case['reference'],case_date=case['date'],
                        valid_date=str(end.date()),year=end.year,season={12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'}[end.month],
                        configuration=meta['configuration'],day=day,station=site['station'],
                        time=str(end-pd.Timedelta(minutes=30)),valid_end=str(end),lead_start=lead,
                        observed_sw=measured,predicted_sw=float(sw[hour,col]),quality=quality,
                        reason=reason,sunshine=sun,snow_cm=snow,model_snow_m=float(model_snow),
                        altitude=site['altitude_m'],model_altitude=float(raw['height'][col]),
                        distance_km=site['distance_km'],observed_latitude=lat,observed_longitude=lon))
    return rows


def scores(frame, groups):
    rows=[]
    for key,group in frame.groupby(groups,dropna=False):
        key=key if isinstance(key,tuple) else (key,)
        good=group[group.reason=='usable']
        row=dict(zip(groups,key))
        row.update(requested=len(group),usable=len(good),dates=good.valid_date.nunique(),
                   initializations=good.reference.nunique(),stations=good.station.nunique())
        if len(good):
            row.update(metric(good.observed_sw.to_numpy(),good.predicted_sw.to_numpy()))
            daily=good.assign(error=good.predicted_sw-good.observed_sw).groupby('valid_date').error
            row['equal_day_bias']=float(daily.mean().mean())
            row['equal_day_mae']=float(daily.apply(lambda a: a.abs().mean()).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    verify_inputs(INPUT,INPUT/'frozen_inputs.json')
    OUTPUT.mkdir(exist_ok=True)
    cfg=json.loads((INPUT/'campaign.json').read_text())
    if len({c['reference'] for c in cfg['cases']})!=len(cfg['cases']):
        raise ValueError('Duplicate initializations in campaign')
    rows=[];ledger=[]
    for case in cfg['cases']:
        try:
            values=case_rows(case,cfg)
            good=sum(row['reason']=='usable' and row['day']==0 for row in values)
            rows.extend(values)
            ledger.append(dict(**case,status='evaluated_sw' if good else 'no_primary_pairs',primary_pairs=good))
        except (ValueError,FileNotFoundError,KeyError) as error:
            ledger.append(dict(**case,status='unavailable',primary_pairs=0,error=str(error)))
    pd.DataFrame(ledger).to_csv(OUTPUT/'case_coverage.csv',index=False)
    frame=pd.DataFrame(rows)
    if frame.empty:
        raise ValueError('No case outputs; inspect coverage ledger')
    frame['sunshine_regime']=sunshine_regime(frame.sunshine)
    frame['snow_regime']=np.select([frame.snow_cm==0,frame.snow_cm>0],['Snow-free','Measured snow'],default='Unknown snow')
    frame['altitude_band']=pd.cut(frame.altitude,[-np.inf,800,1800,np.inf],right=False,labels=['<800 m','800–1800 m','>=1800 m']).astype(str)
    frame.to_csv(OUTPUT/'pairs.csv',index=False)
    for name,groups in [('overall',['day']),('season',['day','season']),('year_season',['day','year','season']),
                        ('sunshine',['day','sunshine_regime']),('snow',['day','snow_regime']),
                        ('altitude',['day','altitude_band']),('configuration',['day','configuration']),
                        ('daily',['day','valid_date']),('station',['day','station']),
                        ('season_sunshine',['day','season','sunshine_regime'])]:
        scores(frame,groups).to_csv(OUTPUT/f'{name}.csv',index=False)
    frame.groupby(['day','reason']).size().rename('count').to_csv(OUTPUT/'exclusions.csv')
    identity=dict(created=datetime.now(timezone.utc).isoformat(),requested_cases=len(ledger),
                  evaluated_sw_cases=sum(r['status']=='evaluated_sw' for r in ledger),
                  evaluated_full_uv_cases=0,source='MeteoSwiss ICON-CH2 control archive; SwissMetNet DWH',
                  code={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        [Path(__file__),ROOT/'analysis/extract_multiyear.py',ROOT/'analysis/MULTIYEAR_PLAN.md',ROOT/'analysis/multiyear_cases.csv']},
                  frozen_manifest_sha256=hashlib.sha256((INPUT/'frozen_inputs.json').read_bytes()).hexdigest())
    (OUTPUT/'run_identity.json').write_text(json.dumps(identity,indent=2))
    print(json.dumps(identity,indent=2))
    print(pd.read_csv(OUTPUT/'overall.csv').to_string(index=False))


if __name__=='__main__':
    main()
