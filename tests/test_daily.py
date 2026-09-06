import json

import numpy as np
import pytest
import xarray as xr

from icon_uv.daily import (daily_cells, daylight_hours, display_value, export_daily as _export_daily,
                           local_day_bounds, select_support, write_json_atomic)


def export_daily(*args, **kwargs):
    return _export_daily(*args, input_sha256='0'*64, **kwargs)


class AnalyticTable:
    sha256 = 'analytic-fixture'

    def at(self, z, ozone, pressure, aod, albedo, tau):
        # Known positive daytime signal: geometry still determines darkness.
        out = np.zeros(np.broadcast_arrays(z, ozone)[0].shape + (4,))
        out[..., 2] = np.where(z < 90, .125, 0)
        return out


def grid(day='2026-09-06', n=6):
    start, end = local_day_bounds(day)
    hours = np.arange(start, end+np.timedelta64(24, 'h'), np.timedelta64(1, 'h'))
    shape = (len(hours), n)
    ds = xr.Dataset(coords={'time': hours+np.timedelta64(30, 'm'), 'cell': np.arange(n)})
    ds['time_bounds'] = (('time', 'bounds'), np.column_stack([hours, hours+np.timedelta64(1, 'h')]))
    for name, val in [('ozone_du', 300), ('aod550', .1), ('pressure_pa', 90000),
                      ('uv_albedo', .05), ('effective_cloud_tau550', 0), ('cloud_scale', 1), ('quality_flag', 0)]:
        ds[name] = (('time', 'cell'), np.full(shape, val, dtype=float))
        ds[name].attrs['units'] = 'Pa' if name == 'pressure_pa' else 'DU' if name == 'ozone_du' else '1'
    for name, val in [('latitude', 46.8), ('longitude', 9.8), ('altitude_m', 1000)]:
        ds[name] = ('cell', np.full(n, val))
    ds.attrs.update(radiation_table_sha256=AnalyticTable.sha256,
                    forecast_reference_time=str(start)+'Z', cams_reference_time=str(start)+'Z')
    return ds


@pytest.mark.parametrize('value,integer,category', [(0,0,'low'),(2.49,2,'low'),(2.5,3,'moderate'),
    (5.5,6,'high'),(7.5,8,'very_high'),(10.5,11,'extreme'),(13.1,13,'extreme')])
def test_display_boundaries(value,integer,category):
    assert display_value(value) == (integer,category)


@pytest.mark.parametrize('value', [-1,float('nan'),float('inf')])
def test_invalid_display(value):
    with pytest.raises(ValueError):display_value(value)


@pytest.mark.parametrize('day,hours', [('2026-03-29',23),('2026-10-25',25),('2026-09-06',24)])
def test_local_day_dst(day,hours):
    start,end=local_day_bounds(day)
    assert (end-start)/np.timedelta64(1,'h') == hours
    h,required=daylight_hours(day,np.array([46.8]),np.array([9.8]))
    assert len(h)==hours and required.any() and not required.all()


def test_complete_peak_and_daylight_gap():
    ds=grid();table=AnalyticTable()
    result=daily_cells(ds,'2026-09-06',table,chunk_size=2)
    assert result['available'].all()
    # Constant daytime UVI=5, multiplied by the physically retained Earth-Sun factor.
    assert np.all((result['uvi']>4.7)&(result['uvi']<5.3))
    assert np.all(result['uvi']>=result['hourly_max_uvi'])
    missing=ds.isel(time=ds.time.dt.hour.values!=11)
    assert not daily_cells(missing,'2026-09-06',table)['available'].any()
    assert np.isnan(daily_cells(missing,'2026-09-06',table)['uvi']).all()
    night=ds.isel(time=ds.time.dt.hour.values!=0)
    assert daily_cells(night,'2026-09-06',table)['available'].all()


def test_reject_corrupt_intervals_units_and_flags():
    ds=grid();table=AnalyticTable()
    for field,value in [('cloud_scale',-1),('ozone_du',np.nan),('quality_flag',.5)]:
        changed=ds.copy(deep=True);changed[field].values[0,0]=value
        with pytest.raises(ValueError):daily_cells(changed,'2026-09-06',table)
    shifted=ds.assign_coords(time=ds.time+np.timedelta64(1,'m'))
    with pytest.raises(ValueError,match='midpoint'):daily_cells(shifted,'2026-09-06',table)
    duplicate=ds.isel(time=[0,0,1])
    with pytest.raises(ValueError,match='nonoverlapping'):daily_cells(duplicate,'2026-09-06',table)
    wrong=ds.copy(deep=True);wrong.pressure_pa.attrs['units']='hPa'
    with pytest.raises(ValueError,match='units'):daily_cells(wrong,'2026-09-06',table)


@pytest.mark.parametrize('cells', [[.1,.2,.3,.4,.5,.6], [-1,0,1,2,3,4]])
def test_native_identifiers_cannot_be_truncated_or_negative(cells):
    # JSON source IDs are integers: accepting fractions would silently alias cells.
    with pytest.raises(ValueError, match='cell identifiers'):
        export_daily(grid().assign_coords(cell=cells), catalog(),
                     '2026-09-06T06:00:00Z', table=AnalyticTable())


def catalog():
    return {'entries':[
        {'id':'town','kind':'town','latitude':46.8,'longitude':9.8,'altitude_m':1000},
        {'id':'region','kind':'region_altitude','bbox':[9.7,46.7,9.9,46.9],'altitude_m':1000},
        {'id':'unsupported','kind':'region_altitude','bbox':[9.7,46.7,9.9,46.9],'altitude_m':3000}]}


def test_native_support_and_export_failure_states():
    ds=grid();table=AnalyticTable();c=catalog()
    payload=export_daily(ds,c,'2026-09-06T06:00:00Z',table=table)
    assert len(payload['entries'])==6
    assert [r['status'] for r in payload['entries'][:3]]==['ok','ok','unavailable']
    assert payload['entries'][2]['display_uvi'] is None
    assert payload['entries'][0]['source_point']['altitude_m']==1000
    assert json.dumps(payload,allow_nan=False)
    assert payload==export_daily(ds,c,'2026-09-06T06:00:00Z',table=table)
    stale=export_daily(ds,c,'2026-09-08T06:00:00Z',table=table)
    assert all(r['status']=='unavailable' and 'stale_icon' in r['reasons'] for r in stale['entries'])
    with pytest.raises(ValueError,match='later than issuance'):
        export_daily(ds,c,'2026-09-05T06:00:00Z',table=table)
    with pytest.raises(ValueError,match='timezone'):
        export_daily(ds,c,'2026-09-06T06:00:00',table=table)
    moved=dict(c['entries'][0],altitude_m=1500)
    assert len(select_support(ds,moved))==0


def test_partial_region_and_atomic_json(tmp_path):
    ds=grid(n=20);table=AnalyticTable()
    # A daylight gap affecting all cells must not become a partial-day maximum.
    ds=ds.isel(time=ds.time.dt.hour.values!=12)
    payload=export_daily(ds,catalog(),'2026-09-06T06:00:00Z',table=table)
    assert payload['entries'][1]['status']=='unavailable'
    assert 'incomplete_daylight' in payload['entries'][1]['reasons']
    path=tmp_path/'product.json';write_json_atomic({'old':1},path)
    with pytest.raises(ValueError):write_json_atomic({'new':np.nan},path)
    assert json.loads(path.read_text())=={'old':1}
    write_json_atomic(payload,path)
    assert json.loads(path.read_text())==payload


def test_region_95_percent_coverage_boundary(monkeypatch):
    ds=grid(n=20)
    def result(available):
        return dict(available=np.array(available),uvi=np.arange(20,dtype=float),
                    peak_start=np.full(20,np.datetime64('2026-09-06T12:00','ns')),
                    quality_flag=np.zeros(20,dtype=np.uint16))
    monkeypatch.setattr('icon_uv.daily.daily_cells',lambda *a:result([True]*19+[False]))
    row=export_daily(ds,catalog(),'2026-09-06T06:00:00Z',table=AnalyticTable())['entries'][1]
    assert row['status']=='degraded' and row['valid_cells']==19
    assert row['uvi']==pytest.approx(16.2)
    assert row['display_uvi']==16 and row['category']=='extreme'
    monkeypatch.setattr('icon_uv.daily.daily_cells',lambda *a:result([True]*18+[False]*2))
    row=export_daily(ds,catalog(),'2026-09-06T06:00:00Z',table=AnalyticTable())['entries'][1]
    assert row['status']=='unavailable' and row['display_uvi'] is None
