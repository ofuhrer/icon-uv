"""Saved-input preflight predicts coverage without calculating any UV values."""
import json

import numpy as np
import pytest
import xarray as xr

from icon_uv.locations import PointLocation, RegionBand
from icon_uv.preflight import preflight
from icon_uv.radiation import DEFAULT_AXES
from test_daily import AnalyticTable, grid
from test_ensemble import stack_members


class NoRadiationTable:
    sha256 = AnalyticTable.sha256
    axes = DEFAULT_AXES

    def at(self, *args):
        raise AssertionError('Preflight must not compute radiation')

    cloud = at


ISSUED = '2026-09-06T06:00:00Z'
POINT = PointLocation('town', 46.8, 9.8, 1000)
REGION = RegionBand('region', (9.7, 46.7, 9.9, 46.9), 1000)


def check(state, locations=(POINT,), **kwargs):
    return preflight(state, locations, ISSUED, table=NoRadiationTable(), days=1, **kwargs)


def test_complete_readonly_preflight_is_json_serializable():
    state = grid()
    original = state.copy(deep=True)
    report = check(state, (POINT, REGION))
    assert report['ready']
    assert report['valid_dates'] == ['2026-09-06']
    assert report['ensemble']['required_member_count'] == 1
    point, region = report['locations']
    assert point['cell_ids'] == [0]
    assert region['selected_cells'] == 6
    day = region['dates'][0]
    assert day['required_daylight_hours'] == day['members'][0]['complete_daylight_hours']
    assert day['members'][0]['complete_cells'] == 6
    json.dumps(report, allow_nan=False)
    xr.testing.assert_identical(state, original)


def test_daylight_gap_is_reported_while_night_gap_is_ignored():
    state = grid()
    night_gap = state.isel(time=np.flatnonzero(state.time.dt.hour.values != 0))
    assert check(night_gap)['ready']
    daylight_gap = state.isel(time=np.flatnonzero(state.time.dt.hour.values != 12))
    report = check(daylight_gap)
    assert not report['ready']
    day = report['locations'][0]['dates'][0]
    assert day['required_daylight_hours'][0] == day['supplied_daylight_hours'][0]+1
    assert day['supplied_daylight_hours'] == day['members'][0]['complete_daylight_hours']
    assert 'incomplete_daylight' in day['reasons']


def test_missing_drivers_are_counted_per_member_cell_before_spatial_coverage():
    members = [grid(n=21) for _ in range(21)]
    for m, state in enumerate(members):
        state.effective_cloud_tau550.values[state.time.dt.hour.values == 12, m//3] = np.nan
    report = check(stack_members(members, list(range(21))), (REGION,))
    assert report['ready']
    assert report['ensemble']['required_member_count'] == 19
    day = report['locations'][0]['dates'][0]
    assert day['complete_member_count'] == 21
    assert all(m['complete_cells'] == 20 for m in day['members'])
    assert 'partial_spatial_support' in day['reasons']
    assert day['members'][0]['complete_daylight_hours'][0] == day['required_daylight_hours'][0]-1
    assert day['supplied_daylight_hours'] == day['required_daylight_hours']


def test_missing_requested_members_are_not_silently_removed():
    state = stack_members([grid(n=1) for _ in range(18)], list(range(18)))
    state.attrs['ensemble_members'] = json.dumps(list(range(21)))
    report = check(state)
    assert not report['ready']
    assert report['ensemble']['required_member_count'] == 19
    day = report['locations'][0]['dates'][0]
    assert day['complete_member_count'] == 18
    assert 'insufficient_ensemble_members' in day['reasons']


def test_unsupported_locations_and_empty_selected_cells_are_graceful():
    absent = PointLocation('absent', 45, 6, 1000)
    report = check(grid(n=3), (absent, REGION))
    assert not report['ready']
    empty, undersized = report['locations']
    assert empty['cell_ids'] == []
    assert empty['support_reason'] == 'insufficient_native_support'
    assert empty['dates'][0]['members'][0]['complete_daylight_hours'] == []
    assert undersized['selected_cells'] == 3
    assert not undersized['supported']
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('field,value', [('ozone_du', 501), ('aod550', 1.1), ('pressure_pa', 105001),
                                        ('uv_albedo', .850001), ('effective_cloud_tau550', 151)])
def test_rejects_outside_table_inputs_with_actionable_context(field, value):
    state = grid()
    state[field].values[0, 0] = value
    with pytest.raises(ValueError, match=f'Source member 0: {field}=.*outside radiation table'):
        check(state)


def test_adjusted_pressure_domain_is_checked_before_reconstruction():
    state = grid()
    state.pressure_pa.values[:] = 70000
    point = PointLocation('summit', 46.8, 9.8, 5000, treatment='adjusted', uv_albedo=.85)
    with pytest.raises(ValueError, match='Location summit, member 0: pressure_pa=.*outside radiation table'):
        check(state, (point,))


def test_stale_sources_are_reported_and_future_sources_rejected():
    state = grid()
    report = preflight(state, (POINT,), '2026-09-09T06:00:00Z', table=NoRadiationTable(), days=1)
    assert not report['ready']
    assert report['reasons'] == ['stale_icon', 'stale_cams']
    with pytest.raises(ValueError, match='later than issuance'):
        preflight(state, (POINT,), '2026-09-05T06:00:00Z', table=NoRadiationTable())


def test_dates_and_state_contract_follow_public_daily_rules():
    assert check(grid(), dates=['2026-09-07'])['valid_dates'] == ['2026-09-07']
    with pytest.raises(ValueError, match='precede'):
        check(grid(), dates=['2026-09-05'])
    state = grid()
    state.ozone_du.attrs['units'] = 'kg m-2'
    with pytest.raises(ValueError, match='units'):
        check(state)
    state = grid()
    del state.attrs['cams_reference_time']
    with pytest.raises(ValueError, match='source metadata cams_reference_time'):
        check(state)


def test_deterministic_slice_uses_single_product_coverage():
    from test_daily import grid, catalog
    from test_ensemble import stack_members
    from icon_uv.radiation import RadiationTable
    ds = grid(n=1)
    ds.attrs['radiation_table_sha256'] = RadiationTable().sha256
    single = stack_members([ds, ds], [0, 1]).sel(member=0, drop=True)
    report = preflight(single, {'entries': [catalog()['entries'][0]]}, '2026-09-06T06:00:00Z', days=1)
    assert report['ready']
    assert report['ensemble']['required_member_count'] == 1
