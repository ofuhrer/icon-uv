"""Calendar coverage and compatibility of the full-horizon daily export."""
from datetime import date
from importlib.resources import files
import json

import numpy as np
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from icon_uv.daily import forecast_dates
from test_daily import AnalyticTable, catalog, export_daily, grid


def forecast(start='2026-09-07T00', hours=120):
    ds = grid()
    times = np.datetime64(start, 'ns') + np.arange(hours)*np.timedelta64(1, 'h')
    ds = ds.isel(time=np.arange(hours) % ds.sizes['time'])
    ds = ds.assign_coords(time=times + np.timedelta64(30, 'm'))
    ds['time_bounds'] = (('time', 'bounds'), np.column_stack([times, times+np.timedelta64(1, 'h')]))
    ds.attrs.update(forecast_reference_time=start+':00:00Z', cams_reference_time=start+':00:00Z')
    return ds


def test_full_horizon_excludes_trailing_night_and_preserves_two_day_values():
    ds = forecast(); table = AnalyticTable(); table.sha256 = 'a'*64
    ds.attrs['radiation_table_sha256'] = table.sha256
    args = (ds, catalog(), '2026-09-07T06:00:00Z')
    old = export_daily(*args, table=table)
    new = export_daily(*args, table=table, days='all')
    assert old['schema'] == 'daily-uv'
    assert new['schema'] == 'daily-uv'
    assert new['valid_dates'] == ['2026-09-07','2026-09-08','2026-09-09','2026-09-10','2026-09-11']
    assert [r for r in new['entries'] if r['day'] < 2] == old['entries']
    assert all(r['status'] == 'ok' for r in new['entries'] if r['location']['kind'] == 'point')
    schema = json.loads(files('icon_uv').joinpath('data/daily-uv.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(new)


def test_partial_last_day_and_internal_gap_remain_unavailable():
    ds = forecast(hours=108)
    ds = ds.isel(time=ds.time.values != np.datetime64('2026-09-09T11:30'))
    result = export_daily(ds, catalog(), '2026-09-07T06:00:00Z', table=AnalyticTable(), days='all')
    assert len(result['valid_dates']) == 5
    towns = [r for r in result['entries'] if r['location']['kind'] == 'point']
    assert [r['day'] for r in towns if r['status'] == 'ok'] == [0, 1, 3]
    assert all(r['uvi'] is None and 'incomplete_daylight' in r['reasons'] for r in towns if r['day'] in (2,4))


@pytest.mark.parametrize('hours,complete_days', [(120, [0, 1, 2, 3]), (48, [0, 1])])
def test_four_day_product_keeps_missing_days_and_omits_fifth(hours, complete_days):
    result = export_daily(forecast(hours=hours), catalog(), '2026-09-07T06:00:00Z',
                          table=AnalyticTable(), days=4)
    assert result['schema'] == 'daily-uv'
    assert result['valid_dates'] == ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10']
    towns = [r for r in result['entries'] if r['location']['kind'] == 'point']
    assert [r['day'] for r in towns if r['status'] == 'ok'] == complete_days
    assert all(r['uvi'] is None and 'incomplete_daylight' in r['reasons']
               for r in towns if r['day'] not in complete_days)


@pytest.mark.parametrize('start,first,expected', [
    ('2026-03-28T00', date(2026,3,28), '2026-04-01'),
    ('2026-10-24T00', date(2026,10,24), '2026-10-28'),
])
def test_forecast_dates_across_dst(start, first, expected):
    dates = forecast_dates(forecast(start), first)
    assert len(dates) == 5 and dates[-1] == expected


def test_no_future_daylight_is_an_error():
    with pytest.raises(ValueError, match='No forecast daylight'):
        forecast_dates(forecast(hours=3), date(2026,9,7))
