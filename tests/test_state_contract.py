"""Reject malformed saved state before any location product reconstructs UV."""
import numpy as np
import pytest

from icon_uv.locations import PointLocation
from icon_uv.data import _validate_cams
from icon_uv.daily import daily_cells
from icon_uv.products import compute_points
from icon_uv.state import SOLAR_SAMPLES, STATE_UNITS, positive_distance, validate_grid
from test_daily import AnalyticTable, grid


@pytest.mark.parametrize('field', STATE_UNITS)
def test_rejects_wrong_units_and_dimension_order(field):
    state = grid()
    state[field].attrs['units'] = 'wrong'
    with pytest.raises(ValueError, match='units'):
        validate_grid(state, AnalyticTable())
    state = grid()
    state[field] = state[field].transpose('cell', 'time')
    with pytest.raises(ValueError, match=r'\(time,cell\)'):
        validate_grid(state, AnalyticTable())


def test_rejects_bounds_shift_missing_or_transposed():
    state = grid()
    state.time_bounds.values[:] += np.timedelta64(1, 'D')
    with pytest.raises(ValueError, match='midpoint'):
        validate_grid(state, AnalyticTable())
    with pytest.raises(ValueError, match='time bounds'):
        validate_grid(grid().drop_vars('time_bounds'), AnalyticTable())
    state = grid()
    state['time_bounds'] = state.time_bounds.transpose('bounds', 'time')
    with pytest.raises(ValueError, match='time bounds'):
        validate_grid(state, AnalyticTable())


@pytest.mark.parametrize('corruption,message', [('units', 'units'), ('bounds', 'midpoint')])
def test_point_and_daily_consumers_reject_same_corrupt_state(corruption, message):
    state = grid()
    state.attrs['solar_samples_per_hour'] = 12
    if corruption == 'units':
        state.ozone_du.attrs['units'] = 'kg m-2'
    else:
        state.time_bounds.values[:] += np.timedelta64(1, 'D')
    poi = PointLocation('test', 46.8, 9.8, 1000., horizon_degrees=(0.,)*4, uv_albedo=.05)
    with pytest.raises(ValueError, match=message):
        compute_points(state, [poi], AnalyticTable())
    with pytest.raises(ValueError, match=message):
        daily_cells(state, '2026-09-06', AnalyticTable())


def test_time_requires_decoded_datetimes_and_native_ids_require_coordinate():
    state = grid()
    state['time_bounds'] = state.time_bounds.astype('int64')
    with pytest.raises(ValueError, match='time bounds'):
        validate_grid(state, AnalyticTable())
    with pytest.raises(ValueError, match='Native cell identifiers'):
        validate_grid(grid().drop_vars('cell'), AnalyticTable())


def test_gaps_and_member_missingness_remain_available_for_coverage_checks():
    state = grid().isel(time=[0, 1, 4])
    bounds = validate_grid(state, AnalyticTable())
    np.testing.assert_array_equal(bounds, state.time_bounds)
    state.effective_cloud_tau550.values[1, 0] = np.nan
    with pytest.raises(ValueError, match='Invalid effective_cloud_tau550'):
        validate_grid(state, AnalyticTable())
    state.attrs['ensemble_members'] = '[0,1]'
    validate_grid(state, AnalyticTable())
    state.quality_flag.values[1, 0] = np.nan
    with pytest.raises(ValueError, match='Invalid quality_flag'):
        validate_grid(state, AnalyticTable())


@pytest.mark.parametrize('samples', [None, True, False, 0, 3, 1.5, '12', np.nan, np.inf])
def test_rejects_invalid_sampling_metadata(samples):
    state = grid()
    state.attrs['solar_samples_per_hour'] = samples
    with pytest.raises(ValueError, match='solar_samples_per_hour'):
        validate_grid(state, AnalyticTable(), require_samples=True)
    validate_grid(state, AnalyticTable())


@pytest.mark.parametrize('samples', SOLAR_SAMPLES)
def test_accepts_supported_sampling_metadata(samples):
    state = grid()
    state.attrs['solar_samples_per_hour'] = np.int64(samples)
    validate_grid(state, AnalyticTable(), require_samples=True)


@pytest.mark.parametrize('distance', [None, '10', True, False, 0, -1, np.nan, np.inf])
def test_rejects_invalid_distance_limits(distance):
    with pytest.raises(ValueError, match='finite and positive'):
        positive_distance(distance)
    assert positive_distance(np.float64(10)) == 10.


@pytest.mark.parametrize('coord,value', [('time', np.datetime64('NaT')), ('latitude', np.nan), ('longitude', np.inf)])
def test_cams_rejects_invalid_coordinates(coord, value):
    from test_uv import cams

    state = cams.__wrapped__()
    values = state[coord].values.copy()
    values[0] = value
    state = state.assign_coords({coord: values})
    with pytest.raises(ValueError, match=f'Invalid CAMS {coord}'):
        _validate_cams(state)


def test_cams_normalizes_order_without_mutating_input():
    from test_uv import cams

    state = cams.__wrapped__().isel(latitude=[1, 0])
    normalized = _validate_cams(state)
    np.testing.assert_array_equal(normalized.latitude, [45., 49.])
    np.testing.assert_array_equal(state.latitude, [49., 45.])
