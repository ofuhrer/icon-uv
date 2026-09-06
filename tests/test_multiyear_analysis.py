"""Scientific contract checks for the historical archive adapter."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

root = Path(__file__).resolve().parents[1]
# Repository analysis is intentionally not an installed runtime dependency.
sys.path.insert(0, str(root))
from analysis.multiyear import read_observations, reconstructed_sw, scores
sys.path.pop(0)


def test_campaign_has_150_unique_dates_spanning_years_and_all_seasons():
    cases = pd.read_csv(root/'analysis/multiyear_cases.csv')
    assert len(cases) == cases.reference.nunique() == cases.date.nunique() == 150
    assert cases.year.value_counts().to_dict() == {2025:72, 2026:48, 2024:30}
    assert set(cases.season) == {'DJF','MAM','JJA','SON'}
    assert cases.groupby(['year','month']).size().eq(6).all()
    assert pd.to_datetime(cases.date).diff().dropna().min() >= pd.Timedelta(days=3)
    assert all(pd.to_datetime(cases.reference).dt.hour == 0)


def test_dwh_repeated_quality_headers_stay_with_correct_parameter(tmp_path):
    path=tmp_path/'obs.csv'
    path.write_text('station;termin;nat_abbr;gre000h0;dq;sre000h0;dq\n'
                    '26;20250103090000;DAV;125;4;12;2\n')
    obs=read_observations(path).loc[('DAV',pd.Timestamp('2025-01-03 09:00'))]
    assert obs.gre000h0==125 and obs.gre000h0_quality==4
    assert obs.sre000h0==12 and obs.sre000h0_quality==2
    assert pd.isna(obs.htoauths)


def test_duplicate_station_hour_is_rejected(tmp_path):
    path=tmp_path/'obs.csv'
    path.write_text('station;termin;nat_abbr;gre000h0;dq\n'+'26;20250103090000;DAV;125;4\n'*2)
    with pytest.raises(ValueError,match='Duplicate station-hour'):
        read_observations(path)


def test_hourly_direct_plus_diffuse_recovers_known_energy_and_rejects_reset():
    # Cumulative means: the 8-9 hour direct irradiance is 190; diffuse is 100.
    raw=dict(leads=np.array([8,9]),direct=np.array([[100.],[110.]]),diffuse=np.array([[50.],[500/9]]))
    records=[dict(field=f,endStep=h,packingError=0.) for h in [8,9] for f in ['direct','diffuse']]
    assert reconstructed_sw(raw,records,[8,9])[0,0]==pytest.approx(290.)
    with pytest.raises(ValueError,match='Missing or duplicate'):
        reconstructed_sw(raw,records[:-1],[8,9])
    raw['direct'][1,0]=0
    with pytest.raises(ValueError,match='Negative hourly energy'):
        reconstructed_sw(raw,records,[8,9])


def test_metrics_count_cases_not_station_hours_and_keep_exclusions():
    frame=pd.DataFrame(dict(day=[0]*4,reason=['usable']*3+['observation_quality'],
        valid_date=['2025-01-03']*2+['2025-01-08']*2,reference=['a']*2+['b']*2,
        station=['DAV','PAY','DAV','PAY'],observed_sw=[100,100,100,100],predicted_sw=[110,110,140,999]))
    out=scores(frame,['day']).iloc[0]
    assert out.requested==4 and out.usable==3 and out.initializations==2 and out.dates==2
    assert out.bias==20 and out.equal_day_bias==25


def test_uv_hourly_integration_brackets_endpoints_and_rejects_long_gaps():
    sys.path.insert(0,str(root))
    from analysis.multiyear_uv import integrate_hour
    sys.path.pop(0)
    start=pd.Timestamp('2025-01-03 08:00')
    seconds=np.arange(-10,3611,10)
    series=pd.Series(1+seconds/3600,index=start+pd.to_timedelta(seconds,unit='s'))
    value,reason,_=integrate_hour(series,start)
    assert reason=='usable' and value==pytest.approx(1.5)
    _,reason,_=integrate_hour(series.drop(series.index[4:8]),start)
    assert reason=='gap_exceeds_cadence_limit'
    _,reason,_=integrate_hour(series.iloc[2:],start)
    assert reason=='no_boundary_bracket'
    series.iloc[12]=np.nan
    _,reason,_=integrate_hour(series,start)
    assert reason=='invalid_sample'


def test_minute_uv_cadence_accepts_complete_record_but_not_missing_minute():
    sys.path.insert(0,str(root))
    from analysis.multiyear_uv import integrate_hour,source_cadence
    sys.path.pop(0)
    start=pd.Timestamp('2025-01-03 08:00')
    seconds=np.arange(-59,3662,60)
    series=pd.Series(2.,index=start+pd.to_timedelta(seconds,unit='s'))
    nominal,limit=source_cadence(series)
    assert nominal==60 and limit==75
    assert integrate_hour(series,start,limit)[:2]==(2.,'usable')
    assert integrate_hour(series.drop(series.index[10]),start,limit)[1]=='gap_exceeds_cadence_limit'
