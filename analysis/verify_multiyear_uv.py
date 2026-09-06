"""Independent raw-segment integration and scalar UV score reconciliation."""
import csv
import io
import json
import math

import numpy as np
import pandas as pd

from analysis.multiyear import INPUT,OUTPUT
from analysis.scientific import verify_inputs


def main():
    verify_inputs(INPUT/'uv',INPUT/'uv/frozen_inputs.json')
    pairs=pd.read_csv(OUTPUT/'uv_pairs.csv')
    manifest=json.loads((INPUT/'uv/woudc_manifest.json').read_text())['inputs']
    checked=0;maximum=0.
    for record in manifest:
        rows=pairs[(pairs.case_date==record['case_date'])&(pairs.day==record['day'])&np.isfinite(pairs.observed_uvi)]
        if rows.empty:continue
        lines=(INPUT/'uv/woudc'/record['path']).read_text().splitlines()
        start=lines.index('#GLOBAL')+1
        end=next((i for i in range(start,len(lines)) if lines[i].startswith('#')),len(lines))
        data=list(csv.DictReader(io.StringIO('\n'.join(lines[start:end]))))
        times=np.array([sum(int(v)*w for v,w in zip(r['Time'].split(':'),(3600,60,1))) for r in data],float)
        values=np.array([float(r['Irradiance'])*40 for r in data])
        for row in rows.itertuples():
            hour=pd.Timestamp(row.time).hour;lower=hour*3600;upper=lower+3600
            # Integrate each intersecting linear segment analytically rather
            # than interpolate endpoints and call a trapezoid implementation.
            active=(times[:-1]<upper)&(times[1:]>lower)
            x=times[:-1][active];y=values[:-1][active]
            dx=np.diff(times)[active];slope=np.diff(values)[active]/dx
            a=np.maximum(x,lower)-x;b=np.minimum(x+dx,upper)-x
            integral=math.fsum((y*(b-a)+.5*slope*(b*b-a*a)).tolist())/3600
            maximum=max(maximum,abs(integral-row.observed_uvi));checked+=1
    assert checked>0 and maximum<1e-9
    metrics_checked=0
    for name,keys in [('overall',['day']),('season',['day','season']),('snow',['day','snow_regime'])]:
        for record in pd.read_csv(OUTPUT/f'uv_{name}.csv').to_dict('records'):
            selected=pairs[(pairs.reason=='usable')&np.isfinite(pairs[record['product']])]
            for key in keys:selected=selected[selected[key]==record[key]]
            errors=(selected[record['product']]-selected.observed_uvi).to_list();n=len(errors)
            assert n==record['usable']
            if n:
                expected=dict(bias=math.fsum(errors)/n,mae=math.fsum(map(abs,errors))/n,
                              rmse=math.sqrt(math.fsum(e*e for e in errors)/n))
                assert all(abs(record[k]-v)<1e-9 for k,v in expected.items())
                metrics_checked+=3
    result=dict(status='passed',raw_integrations_checked=checked,max_integration_difference=maximum,
                scalar_metrics_checked=metrics_checked,primary_initializations=pairs[(pairs.day==0)&(pairs.reason=='usable')].reference.nunique())
    (OUTPUT/'uv_verification.json').write_text(json.dumps(result,indent=2));print(result)


if __name__=='__main__':main()
