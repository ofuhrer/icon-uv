"""Observation support checks independent of model agreement."""
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis.swiss_uv_analysis import interval_means


def test_mean_support_weights_and_time_phase():
    # Centred minute means at 00:00, 00:01, 00:02 contribute 30/60/30 s.
    s=pd.Series([0.,2.,4.],index=pd.date_range('2025-01-01',periods=3,freq='min'))
    start=np.array(['2025-01-01T00:00'],dtype='datetime64[s]')
    assert interval_means(s,start,duration=120)[0]==2
    assert interval_means(s,start,duration=120,phase=30)[0]==1
    assert interval_means(s,start,duration=120,phase=-30)[0]==3


def test_missing_or_invalid_minute_does_not_become_partial_mean():
    times=pd.date_range('2025-01-01',periods=32,freq='min')
    s=pd.Series(np.ones(32),index=times)
    start=np.array(['2025-01-01T00:00:30'],dtype='datetime64[s]')
    assert interval_means(s,start)[0]==1
    assert np.isnan(interval_means(s.drop(times[12]),start)[0])
    s.iloc[12]=np.nan
    assert np.isnan(interval_means(s,start)[0])
    s.iloc[12]=-0.01
    assert np.isnan(interval_means(s,start)[0])
    with pytest.raises(ValueError,match='duplicate'):
        interval_means(pd.concat([s,s]),start)


def test_exact_boundaries_do_not_require_adjacent_invalid_bins():
    s=pd.Series([np.nan,3.,np.nan],index=pd.date_range('2025-01-01',periods=3,freq='min'))
    assert interval_means(s,np.array(['2025-01-01T00:00:30'],dtype='datetime64[s]'),duration=60)[0]==3


def test_missing_shortwave_placeholder_cannot_score_as_zero_uv():
    import xarray as xr
    from analysis.swiss_uv_analysis import halfhours
    starts=np.array(['2025-06-21T10:00','2025-06-21T11:00'],dtype='datetime64[s]')
    g=xr.Dataset(coords={'time':starts,'cell':[1]})
    g['time_bounds']=(('time','bounds'),np.column_stack([starts,starts+np.timedelta64(1,'h')]))
    g['latitude']=('cell',[46.8]);g['longitude']=('cell',[9.8])
    for field,value in [('ozone_du',300),('pressure_pa',90000),('aod550',.1),('uv_albedo',.05),('effective_cloud_tau550',0),('cloud_scale',1)]:
        g[field]=(('time','cell'),np.full((2,1),value))
    g['sw_available']=('time',[True,False])
    class ConstantUV:
        def at(self,z,*args):
            output=np.zeros(z.shape+(4,));output[...,2]=.1;return output
    result=halfhours(g,ConstantUV())
    assert np.isfinite(result[:2]).all()
    assert np.isnan(result[2:]).all()
