"""Reconcile published pairs with boundary data and raw observation columns."""
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.multiyear import INPUT, OUTPUT
from analysis.scientific import verify_inputs


def main():
    verify_inputs(INPUT,INPUT/'frozen_inputs.json')
    cfg=json.loads((INPUT/'campaign.json').read_text())
    pairs=pd.read_csv(OUTPUT/'pairs.csv',dtype={'configuration':str})
    keys=['reference','station','valid_end']
    if pairs.duplicated(keys).any():raise AssertionError('Duplicate forecast-observation pairs')
    max_flux_error=0.;max_obs_error=0.;checked=0
    for case in cfg['cases']:
        date=case['date'].replace('-','')
        frame=pairs[pairs.reference==case['reference']].set_index(['station','valid_end'])
        with np.load(INPUT/'icon'/f'{date}_00.npz') as source:
            leads=source['leads'].tolist()
            for day in (0,1):
                observation_file=INPUT/'observations'/f'{date}_day{day}.csv'
                with observation_file.open() as stream:
                    reader=csv.reader(stream,delimiter=';');header=next(reader)
                    st=header.index('nat_abbr');ti=header.index('termin');va=header.index('gre000h0')
                    observations={(r[st],datetime.strptime(r[ti],'%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')):(r[va],r[va+1]) for r in reader}
                for lead in range(8+day*24,16+day*24):
                    lo,hi=leads.index(lead),leads.index(lead+1)
                    end=(pd.Timestamp(case['date'])+pd.Timedelta(hours=lead+1)).strftime('%Y-%m-%d %H:%M:%S')
                    for column,site in enumerate(cfg['stations']):
                        row=frame.loc[(site['station'],end)]
                        expected=max(0.,(lead+1)*(source['direct'][hi,column]+source['diffuse'][hi,column])
                                     -lead*(source['direct'][lo,column]+source['diffuse'][lo,column]))
                        max_flux_error=max(max_flux_error,abs(expected-row.predicted_sw))
                        raw=observations.get((site['station'],end))
                        if raw and raw[0]:
                            max_obs_error=max(max_obs_error,abs(float(raw[0])-row.observed_sw))
                            assert float(raw[1])==row.quality if raw[1] else pd.isna(row.quality)
                        else:assert pd.isna(row.observed_sw)
                        checked+=1
    assert max_flux_error<1e-8 and max_obs_error==0
    for summary,keys in [('overall',['day']),('season',['day','season']),('year_season',['day','year','season'])]:
        for record in pd.read_csv(OUTPUT/f'{summary}.csv').to_dict('records'):
            selected=pairs[pairs.reason=='usable']
            for key in keys:selected=selected[selected[key]==record[key]]
            errors=(selected.predicted_sw-selected.observed_sw).to_list();n=len(errors)
            assert n==record['usable'] and selected.reference.nunique()==record['initializations']
            if n:
                expected={'bias':math.fsum(errors)/n,'mae':math.fsum(map(abs,errors))/n,
                          'rmse':math.sqrt(math.fsum(v*v for v in errors)/n)}
                assert all(abs(record[k]-v)<1e-9 for k,v in expected.items())
    result=dict(status='passed',pairs_checked=checked,max_boundary_flux_error=max_flux_error,
                max_raw_observation_error=max_obs_error,unique_initializations=pairs.reference.nunique())
    (OUTPUT/'verification.json').write_text(json.dumps(result,indent=2));print(result)


if __name__=='__main__':main()
