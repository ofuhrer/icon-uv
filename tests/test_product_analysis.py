from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis.product_analysis import observed_peak
from analysis.product_metrics import product_scores,date_block_indices


def test_observed_peak_integrates_and_rejects_daylight_gap():
    t=pd.date_range('2025-06-15',periods=8641,freq='10s')
    # A triangular pulse centred at noon: exact 30-min mean is 5.875;
    # exact clock-hour mean is 5.5. Night values are valid zero.
    hours=(t-t[0]).total_seconds().to_numpy()/3600
    values=np.maximum(0,6-abs(hours-12))
    series=pd.Series(values,index=t)
    peak=observed_peak(series,'2025-06-15')
    assert peak['reason']=='usable'
    assert peak['uvi']==pytest.approx(5.875,abs=1e-9)
    assert peak['hourly']==pytest.approx(5.5,abs=1e-9)
    # Whole UTC hours 11-12 and 12-13 each average 5.5.
    missing=series.drop(series.loc['2025-06-15 08:15':'2025-06-15 08:16'].index)
    assert observed_peak(missing,'2025-06-15')['reason']=='daylight_observation_gap'
    broken=series.copy();broken.loc['2025-06-15 10:00']=np.nan
    assert observed_peak(broken,'2025-06-15')['reason']=='invalid_daylight_irradiance'


def test_product_metrics_category_and_threshold_denominators():
    result=product_scores([2,3,8,11],[2,2,3,12])
    assert result['within_one']==.75
    assert result['same_category']==.5
    assert result['under_two_categories']==.25
    assert result['observed_ge_3']==3
    assert result['miss_ge_3']==pytest.approx(1/3)
    assert result['very_high_forecast_below_high']==.5
    assert product_scores([0],[0])['miss_ge_11'] is None


def test_bootstrap_keeps_sites_paired_and_seasons_fixed():
    dates=np.repeat(['2025-01-03','2025-01-08','2025-06-03','2025-06-08'],2)
    season=np.repeat(['DJF','DJF','JJA','JJA'],2)
    indices=list(date_block_indices(dates,season,repeats=10))
    assert all(len(i)==8 for i in indices)
    for i in indices:
        assert sum(season[i]=='DJF')==4
        assert all(np.sum(i==j)==np.sum(i==j+1) for j in (0,2,4,6))
    again=list(date_block_indices(dates,season,repeats=10))
    assert all(np.array_equal(a,b) for a,b in zip(indices,again))
