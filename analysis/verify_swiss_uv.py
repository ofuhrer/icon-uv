"""Independent arithmetic/source checks of the Swiss validation artifacts."""
import argparse
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd


def run(root):
    out=root/'results';d=pd.read_csv(out/'daily_pairs.csv');w=pd.read_csv(out/'window_pairs.csv')
    checked={};max_source_error=0.0
    unique=w.drop_duplicates(['reference','site','time'])
    # Separate parser: explicit offset conversion and raw JSON measurement dictionary.
    for (reference,site),g in unique[unique.site!='PAY'].groupby(['reference','site']):
        stem=reference[:10].replace('-','')
        raw=json.loads((root/'imed'/f'{stem}.json').read_text())[site]['uve']
        assert raw['unit']=='UV-Index'
        mapping={datetime.fromisoformat(t.replace('Z','+00:00')).astimezone(timezone.utc).replace(tzinfo=None):v
                 for t,v in zip(raw['ts'],raw['measurement'])}
        for r in g.itertuples():
            error=abs(mapping[datetime.fromisoformat(r.time)]-r.observed_uvi)
            assert error<1e-12;max_source_error=max(max_source_error,error)
    checked['imed_source_windows']=int((unique.site!='PAY').sum())
    # Separate BSRN parser and explicit 31-bin overlap weights. No analysis adapter.
    pay=unique[unique.site=='PAY'].copy();pay['month']=pay.time.str[:7].str.replace('-','')
    rolling_checks=0
    for month,g in pay.groupby('month'):
        text=(root/'payerne'/f'{month}_uv.tab').read_text().split('*/\n',1)[1]
        raw={datetime.fromisoformat(r['Date/Time']):r['UV-b global [W/m**2]']
             for r in csv.DictReader(io.StringIO(text),delimiter='\t')}
        for r in g.itertuples():
            start=datetime.fromisoformat(r.time)-timedelta(minutes=15)
            v=[float(raw[start+timedelta(minutes=i)])*40 for i in range(31)]
            expected=(0.5*v[0]+sum(v[1:-1])+0.5*v[-1])/30
            error=abs(expected-r.observed_uvi);assert error<1e-10
            max_source_error=max(max_source_error,error)
        # Independent rolling-peak reconstruction from minute records. Search the
        # entire 03:00–21:00 support, including night, without the analysis adapter.
        days=d[(d.site=='PAY')&(d['product']=='native')&(d.reason=='usable')&
               (d.valid_date.str[:7].str.replace('-','')==month)]
        for r in days.itertuples():
            start=datetime.fromisoformat(r.valid_date)+timedelta(hours=3)
            peaks=[[],[],[]]
            for step in range(0,1051,5):
                t=start+timedelta(minutes=step)
                v=np.array([float(raw.get(t+timedelta(minutes=i),'nan') or 'nan')*40 for i in range(31)])
                if not np.isfinite(v).all() or (v<0).any():continue
                peaks[0].append(v[1:].mean())
                peaks[1].append((v[0]/2+sum(v[1:-1])+v[-1]/2)/30)
                peaks[2].append(v[:-1].mean())
            maxima=np.array([max(p) for p in peaks])
            assert abs(maxima[1]-r.rolling_observed_uvi)<1e-10
            assert abs(maxima.min()-r.rolling_phase_low)<1e-10
            assert abs(maxima.max()-r.rolling_phase_high)<1e-10
            rolling_checks+=1
    checked['payerne_source_windows']=len(pay)
    checked['payerne_rolling_days']=rolling_checks
    # Every accepted daily half-hour peak is recoverable from the published pairs.
    grouped=w.groupby(['reference','day','site','product'])
    for r in d[d.reason=='usable'].itertuples():
        g=grouped.get_group((r.reference,r.day,r.site,r.product))
        assert len(g)==r.required_windows
        assert abs(g.observed_uvi.max()-r.observed_uvi)<1e-10
        assert abs(g.predicted_uvi.max()-r.predicted_uvi)<1e-10
        assert r.rolling_predicted_uvi+1e-10>=r.predicted_uvi
        if np.isfinite(r.observed_phase_low+r.observed_phase_high):
            assert r.observed_phase_low-1e-10<=r.observed_uvi<=r.observed_phase_high+1e-10
    checked['daily_peak_rows']=int((d.reason=='usable').sum())
    # Independent score arithmetic, without product_scores or its category mapper.
    scores=pd.read_csv(out/'scores.csv');n=0
    for r in scores.itertuples():
        if r.target=='daily_halfhour_grid':source=d[d.reason=='usable']
        elif r.target=='paired_halfhours':source=w
        else:source=w[w.zenith<=70]
        for field in r.stratum.split('/'):
            source=source[source[field]==getattr(r,field)]
        obs=source.observed_uvi.to_numpy();pred=source.predicted_uvi.to_numpy()
        assert len(source)==r.n
        oi=np.floor(obs+.5);pi=np.floor(pred+.5)
        category=lambda a:np.where(a<3,0,np.where(a<6,1,np.where(a<8,2,np.where(a<11,3,4))))
        oc,pc=category(oi),category(pi);delta=pred-obs
        expected=dict(bias=delta.mean(),mae=abs(delta).mean(),absolute_error_p90=np.quantile(abs(delta),.9),
                      within_one=np.mean(abs(pi-oi)<=1),same_category=np.mean(oc==pc),
                      under_two_categories=np.mean(oc-pc>=2))
        for key,value in expected.items():assert abs(value-getattr(r,key))<1e-10;n+=1
    checked['summary_values']=n
    # Each new native field's source message hash must match the older independent
    # extraction for the same case/lead/field, including the overlapping PAY cell.
    old=root.parent/'product-readiness-20260906'/'icon';native_values=0
    for path in (root/'icon').glob('????????_00.npz'):
        a=np.load(path);b=np.load(old/path.name)
        am=json.loads(path.with_suffix('.json').read_text());bm=json.loads((old/path.name).with_suffix('.json').read_text())
        record=lambda m:{(r['field'],r['endStep']):r['sha256'] for r in m['records']}
        assert record(am)==record(bm)
        for col,cell in enumerate(a['cell']):
            cols=np.flatnonzero(b['cell']==cell)
            if not len(cols):continue
            for field in ('direct','diffuse','pressure','albedo','snow_depth','height'):
                aa=a[field][...,col];bb=b[field][...,cols[0]]
                assert np.array_equal(aa,bb,equal_nan=True);native_values+=np.asarray(aa).size
        a.close();b.close()
    checked['overlapping_native_values']=native_values
    checked['max_source_conversion_error']=max_source_error
    checked['status']='passed'
    (out/'verification.json').write_text(json.dumps(checked,indent=2));print(json.dumps(checked,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    run(p.parse_args().root)
