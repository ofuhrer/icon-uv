"""Independent scalar arithmetic and raw-source checks of expanded results."""
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import unquote
import csv
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'work/scientific-hardening-20260906'
RESULT=DATA/'results'


def read(name):
    with (RESULT/name).open() as stream: return list(csv.DictReader(stream))


def check():
    evidence=[]
    manifest=json.loads((DATA/'frozen_inputs.json').read_text())
    for entry in manifest['inputs']:
        assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256']
    evidence.append(f"{len(manifest['inputs'])} frozen input hashes verified independently")
    raw=json.loads((DATA/'uv_8days.json').read_text())
    original={}
    for key,content in raw.items():
        series=content['uve']
        original[unquote(key)]={datetime.fromisoformat(t.replace('Z','+00:00')).replace(tzinfo=None):v
                               for t,v in zip(series['ts'],series['measurement'])}
    forecast,historical=read('forecast_pairs.csv'),read('historical_pairs.csv')
    for name,rows,keys in [('forecast',forecast,['site','cycle','time']),('historical',historical,['site','time'])]:
        assert len(rows)==len({tuple(r[k] for k in keys) for r in rows})
        usable=0
        for row in rows:
            mid=datetime.fromisoformat(row['time']); times=[mid+timedelta(minutes=k) for k in [-15,15]]
            values=[original.get(row['site'],{}).get(t) for t in times]
            complete=all(v is not None and math.isfinite(v) and v>=0 for v in values)
            assert complete==(row['uv_reason']=='usable')
            if complete:
                assert math.isclose(float(row['observed_uvi']),sum(values)/2,abs_tol=1e-12)
                usable+=1
        evidence.append(f"{name}: {len(rows)} unique rows; {usable} usable UV pairs reconcile to raw API timestamps")
    def score(rows,predicted,observed):
        pairs=[(float(r[observed]),float(r[predicted])) for r in rows if r[observed] and r[predicted]]
        errors=[p-o for o,p in pairs]
        if not errors: return {'n':0}
        n=len(errors)
        return dict(n=n,bias=sum(errors)/n,mae=sum(abs(e) for e in errors)/n,
                    rmse=math.sqrt(sum(e*e for e in errors)/n))
    def reconcile(summary_name,rows,keys,observed):
        for summary in read(summary_name):
            selected=[r for r in rows if all(r[k]==summary[k] for k in keys)]
            recalculated=score(selected,summary['product'],observed)
            for name,value in recalculated.items():
                assert math.isclose(value,float(summary[name]),abs_tol=1e-9), (summary_name,name)
    fp=[r for r in forecast if 8<=float(r['hour'])<16]
    hp=[r for r in historical if 8<=float(r['hour'])<16]
    reconcile('forecast_primary.csv',fp,['cycle','site'],'observed_uvi')
    reconcile('historical_daily.csv',hp,['site','date'],'observed_uvi')
    reconcile('historical_summary.csv',hp,['site'],'observed_uvi')
    evidence.append('All primary forecast and historical daily/pooled bias, MAE and RMSE values independently recomputed')
    region=read('regional_pairs.csv'); primary=[]; sw_sources={}
    for row in region:
        station=row['station']
        if station not in sw_sources:
            with (ROOT/f'work/scientific-validation-20260906/ogd-smn_{station.lower()}_h_now.csv').open() as stream:
                sw_sources[station]={datetime.strptime(r['reference_timestamp'],'%d.%m.%Y %H:%M'):r for r in csv.DictReader(stream,delimiter=';')}
        end=datetime.fromisoformat(row['time'])+timedelta(minutes=30)
        assert float(sw_sources[station][end]['gre000h0'])==float(row['observed_sw'])
        if 8<=datetime.fromisoformat(row['time']).hour<16: primary.append(row)
    reconcile('regional_summary.csv',primary,['cycle'],'observed_sw')
    evidence.append(f'{len(region)} regional shortwave source timestamps and all cycle summary metrics verified')
    for name in ['paired_cycle_errors.csv','regional_paired_errors.csv']:
        matched=read(name)
        key='station' if 'regional' in name else 'site'
        assert len(matched)==len({(r['comparison'],r[key],r['time']) for r in matched})
        for r in matched:
            observed='observed_sw_base' if key=='station' else 'observed_uvi_base'
            base='predicted_sw_base' if key=='station' else 'forecast_uvi_base'
            new='predicted_sw_new' if key=='station' else 'forecast_uvi_new'
            expected=abs(float(r[new])-float(r[observed]))-abs(float(r[base])-float(r[observed]))
            assert math.isclose(expected,float(r['delta_absolute_error']),abs_tol=1e-9)
        evidence.append(f'{name}: {len(matched)} unique paired differences verified')
    # Check pressure conversion against the raw station observation and metadata.
    import pandas as pd
    meta=pd.read_csv(ROOT/'work/scientific-validation-20260906/ogd-smn_meta_stations.csv',sep=';',encoding='cp1252').set_index('station_abbr')
    sites={s['name']:s for s in json.loads((DATA/'uv_sites.json').read_text())}
    for site,code in [('Davos','DAV'),('Weissfluhjoch','WFJ')]:
        source={}
        for path in [DATA/f'ogd-smn_{code.lower()}_h_recent.csv',ROOT/f'work/scientific-validation-20260906/ogd-smn_{code.lower()}_h_now.csv']:
            with path.open() as stream:
                source.update({datetime.strptime(r['reference_timestamp'],'%d.%m.%Y %H:%M'):r for r in csv.DictReader(stream,delimiter=';')})
        for row in [r for r in historical if r['site']==site]:
            end=datetime.fromisoformat(row['time'])+timedelta(minutes=30)
            expected=float(source[end]['prestah0'])*100*math.exp(-(sites[site]['altitude']-float(meta.loc[code,'station_height_barometer_masl']))/8434)
            assert math.isclose(expected,float(row['pressure_pa']),abs_tol=1e-8)
            assert float(source[end]['gre000h0'])==float(row['measured_sw'])
    evidence.append('Historical pressure hPa→Pa conversion, barometer-height adjustment and measured shortwave verified against raw sources')
    result={'status':'passed','checks':evidence,
            'limits':['Numerical/source checks do not certify UV calibration, averaging bounds or per-value QC',
                      'Forecast skill spans one weather day; historical conversion is observation driven',
                      'Shortwave and UV instruments are not colocated; no causal decomposition or iid confidence interval']}
    (RESULT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__': print(json.dumps(check(),indent=2))
