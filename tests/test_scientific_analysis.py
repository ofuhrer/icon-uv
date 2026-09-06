"""Analytically known examples for scientific cohort and provenance safeguards."""
import hashlib
import json
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Analysis remains repository tooling, outside the distributed runtime package.
spec=importlib.util.spec_from_file_location('scientific_analysis',Path(__file__).resolve().parents[1]/'analysis/scientific.py')
science=importlib.util.module_from_spec(spec)
spec.loader.exec_module(science)
hourly_uv,matched_cycle_errors,metric,uv_series,verify_inputs=(
    science.hourly_uv,science.matched_cycle_errors,science.metric,science.uv_series,science.verify_inputs)


def raw_uv(times, values):
    return {'Davos':{'uve':{'unit':'UV-Index','ts':times,'measurement':values}}}


def test_hourly_pair_uses_both_samples_and_preserves_missing_hour():
    raw=raw_uv(['2026-09-05T08:15:00Z','2026-09-05T08:45:00Z','2026-09-05T09:15:00Z'],[2,4,9])
    result=hourly_uv(uv_series(raw,'Davos'),pd.date_range('2026-09-05 08:00',periods=2,freq='h'))
    assert result.observed_uvi.iloc[0]==3
    assert result.time.iloc[0]==pd.Timestamp('2026-09-05 08:30')
    assert result.uv_reason.tolist()==['usable','missing_timestamp']
    assert np.isnan(result.observed_uvi.iloc[1])
    assert result.uv_qc.tolist()==['unconfirmed','unconfirmed']


@pytest.mark.parametrize('values,reason', [([2,None],'nonfinite'),([2,-1],'negative'),([0,0],'usable')])
def test_invalid_measurements_are_not_zero_filled(values,reason):
    series=uv_series(raw_uv(['2026-09-05T08:15:00Z','2026-09-05T08:45:00Z'],values),'Davos')
    row=hourly_uv(series,[pd.Timestamp('2026-09-05 08:00')]).iloc[0]
    assert row.uv_reason==reason
    assert row.observed_uvi==0 if reason=='usable' else np.isnan(row.observed_uvi)


def test_duplicate_or_naive_uv_timestamp_is_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        uv_series(raw_uv(['2026-09-05T08:15:00Z']*2,[1,1]),'Davos')
    with pytest.raises(ValueError,match='UTC offset'):
        uv_series(raw_uv(['2026-09-05T08:15:00'],[1]),'Davos')


def test_offset_timestamps_are_converted_to_utc():
    s=uv_series(raw_uv(['2026-09-05T10:15:00+02:00'],[2]),'Davos')
    assert s.index[0]==pd.Timestamp('2026-09-05 08:15')


def test_unknown_sunshine_is_not_assigned_to_a_measured_regime():
    assert science.sunshine_regime([0,5,5.5,49.5,50,60,np.nan,-1,61]).tolist()==[
        '0–5 min sunshine','0–5 min sunshine','Intermediate sunshine','Intermediate sunshine',
        '50–60 min sunshine','50–60 min sunshine','Unknown sunshine','Unknown sunshine','Unknown sunshine']


def test_metric_uses_raw_sums_and_dose_is_separately_unit_specific():
    m=metric([1,9],[2,10])
    assert m['bias']==1 and m['mae']==1 and m['rmse']==1
    assert m['relative_mean_excess']==pytest.approx(.2)
    assert 'window_dose_error_jm2' not in m
    assert science.matched_uv_dose_error([1,9],[2,10],[1,1])==180
    assert science.matched_uv_dose_error([1,9],[2,10],[.5,1])==135
    with pytest.raises(ValueError,match='positive finite'): science.matched_uv_dose_error([1],[2],[0])
    assert np.isnan(metric([0],[0])['relative_mean_excess'])
    with pytest.raises(ValueError,match='finite pairs'): metric([np.nan],[1])


def test_cycle_comparison_matches_valid_times_before_scoring():
    base=pd.DataFrame(dict(site=['Davos']*3,time=[1,2,3],observed_uvi=[1,2,3],forecast_uvi=[9,4,6]))
    newer=pd.DataFrame(dict(site=['Davos']*2,time=[2,3],observed_uvi=[2,3],forecast_uvi=[3,4]))
    result=matched_cycle_errors(base,newer)
    assert result.time.tolist()==[2,3]
    assert result.base_absolute_error.mean()==2.5
    assert result.new_absolute_error.mean()==1
    assert result.delta_absolute_error.mean()==-1.5
    with pytest.raises(ValueError,match='Duplicate'):
        matched_cycle_errors(pd.concat([base,base.iloc[:1]]),newer)
    newer.loc[0,'observed_uvi']=99
    with pytest.raises(ValueError,match='identical observations'): matched_cycle_errors(base,newer)


def test_frozen_manifest_rejects_tampering_without_rewriting_expected_hash(tmp_path):
    data=tmp_path/'observations.csv';data.write_text('actual input')
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'inputs':[{'path':'observations.csv','sha256':hashlib.sha256(data.read_bytes()).hexdigest()}]}))
    before=manifest.read_bytes()
    verify_inputs(tmp_path,manifest)
    data.write_text('changed input')
    with pytest.raises(ValueError,match='Frozen input changed'): verify_inputs(tmp_path,manifest)
    assert manifest.read_bytes()==before
