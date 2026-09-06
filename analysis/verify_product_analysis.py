"""Independent source bridge and observed daily-peak arithmetic audit."""
import csv
import io
import json
import math

import numpy as np
import pandas as pd

from analysis.product_analysis import INPUT,OLD,OUTPUT
from analysis.scientific import verify_inputs


def main():
    verify_inputs(INPUT,INPUT/'frozen_inputs.json')
    cfg=json.loads((INPUT/'campaign.json').read_text())
    checked=0
    for case in cfg['cases']:
        stem=case['date'].replace('-','')+'_00.npz'
        with np.load(INPUT/'icon'/stem) as new,np.load(OLD/'icon'/stem) as old:
            idx=[list(new['leads']).index(h) for h in old['leads']]
            for name in ('direct','diffuse','pressure','albedo','snow_depth'):
                assert np.array_equal(new[name][idx],old[name],equal_nan=True),(case['date'],name)
                checked+=old[name].size
            assert np.array_equal(new['cell'],old['cell'])
            assert np.array_equal(new['height'],old['height'])
    frame=pd.read_csv(OUTPUT/'daily_pairs.csv');matched=frame[(frame['product']=='native')&(frame.reason=='usable')]
    manifest=json.loads((OLD/'uv/woudc_manifest.json').read_text())['inputs']
    maximum=0.;days=0
    for row in matched.itertuples():
        case_date=str(pd.Timestamp(row.reference).date())
        record=next(r for r in manifest if r['case_date']==case_date and r['day']==row.day)
        lines=(OLD/'uv/woudc'/record['path']).read_text().splitlines()
        start=lines.index('#GLOBAL')+1
        end=next((i for i in range(start,len(lines)) if lines[i].startswith('#')),len(lines))
        raw=list(csv.DictReader(io.StringIO('\n'.join(lines[start:end]))))
        times=np.array([sum(int(x)*k for x,k in zip(r['Time'].split(':'),(3600,60,1))) for r in raw])
        values=np.array([float(r['Irradiance'])*40 for r in raw])
        # Raw time stamps are integer seconds. Every change of linear slope is
        # therefore on this independent 1-second grid, making its trapezoids exact.
        seconds=np.arange(times[0],times[-1]+1)
        dense=np.interp(seconds,times,values)
        total=np.r_[0,np.cumsum((dense[1:]+dense[:-1])*.5)]
        starts=np.arange(int(math.ceil(times[0]/300))*300,times[-1]-1800+1,300)
        means=(total[starts+1800-times[0]]-total[starts-times[0]])/1800
        # Qualified full-day records have no missing daytime peak; nighttime
        # values cannot beat the observed daytime maximum. Check rather than assume.
        independent=float(means.max())
        maximum=max(maximum,abs(independent-row.observed_uvi));days+=1
    assert days>0 and maximum<1e-8,maximum
    metrics=0
    for record in pd.read_csv(OUTPUT/'scores.csv').to_dict('records'):
        selected=frame[frame.reason=='usable']
        for key in record['stratum'].split('/'):
            selected=selected[selected[key]==record[key]]
        if not len(selected):
            assert record['usable']==0;continue
        errors=(selected.predicted_uvi-selected.observed_uvi).tolist();n=len(errors)
        assert n==record['usable']
        assert abs(math.fsum(errors)/n-record['bias'])<1e-10
        assert abs(math.fsum(abs(e) for e in errors)/n-record['mae'])<1e-10
        def category(x):
            integer=math.floor(x+.5)
            return next((i for i,b in enumerate((3,6,8,11)) if integer<b),4)
        obs=selected.observed_uvi.tolist();pred=selected.predicted_uvi.tolist()
        assert abs(sum(abs(math.floor(a+.5)-math.floor(b+.5))<=1 for a,b in zip(obs,pred))/n-record['within_one'])<1e-12
        assert abs(sum(category(a)==category(b) for a,b in zip(obs,pred))/n-record['same_category'])<1e-12
        assert abs(sum(category(a)-category(b)>=2 for a,b in zip(obs,pred))/n-record['under_two_categories'])<1e-12
        metrics+=5
    result=dict(status='passed',unchanged_native_boundary_values=checked,observed_daily_maxima=days,
                maximum_peak_difference=maximum,independent_summary_values=metrics)
    (OUTPUT/'verification.json').write_text(json.dumps(result,indent=2));print(result)


if __name__=='__main__':main()
