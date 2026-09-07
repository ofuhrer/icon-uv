"""Coverage is spatial within members before reduction across member products."""
import numpy as np
import pytest
from icon_uv.daily import daily_cells, export_daily
from test_daily import grid, catalog, AnalyticTable
from test_ensemble import stack_members


def partial_region(clustered):
    parts = [grid(n=21) for _ in range(21)]
    for m, p in enumerate(parts):
        cell = m//3 if clustered else m
        missing = p.time.dt.hour.values == 12
        p.effective_cloud_tau550.values[missing, cell] = np.nan
        p.quality_flag.values[missing, cell] = 128
    return stack_members(parts, list(range(21)))


@pytest.mark.parametrize('clustered', [False, True])
def test_spatial_coverage_within_member_before_ensemble(clustered):
    ds = partial_region(clustered)
    payload = export_daily(ds, catalog(), '2026-09-06T06:00:00Z', input_sha256='0'*64, table=AnalyticTable())
    row = payload['entries'][1]
    assert row['status'] == 'degraded'
    assert row['reasons'] == ['partial_spatial_support']
    assert row['ensemble']['valid_member_count'] == 21
    assert row['ensemble']['member_valid_cells'] == [20]*21
    assert row['valid_cells'] == 21
    assert row['uvi'] > 0
    # Flags describe contributing complete columns, not excluded missing cells.
    assert not row['quality_flag'] & 128
    shuffled = ds.isel(member=list(reversed(range(21))), cell=list(reversed(range(21))))
    other = export_daily(shuffled, catalog(), '2026-09-06T06:00:00Z', input_sha256='0'*64, table=AnalyticTable())['entries'][1]
    assert other['uvi'] == pytest.approx(row['uvi'])
    assert other['status'] == row['status']
    assert set(other['source_cells']) == set(row['source_cells'])


def test_missing_member_does_not_destroy_available_peak_range():
    ds = partial_region(False).isel(cell=[0])
    result = daily_cells(ds, '2026-09-06', AnalyticTable())
    assert result['available'][0]
    assert result['member_count'][0] == 20
    assert not np.isnat(result['peak_start'][0])
    assert not np.isnat(result['peak_start_range'][0]).any()
    ds.effective_cloud_tau550.values[:] = np.nan
    result = daily_cells(ds, '2026-09-06', AnalyticTable())
    assert not result['available'][0]
    assert np.isnat(result['peak_start_range'][0]).all()


def test_excluded_member_extremes_do_not_enter_native_metadata():
    parts = [grid(n=21) for _ in range(21)]
    parts[0].cloud_scale.values[:] = 100
    parts[0].effective_cloud_tau550.values[parts[0].time.dt.hour.values == 12, :2] = np.nan
    ds = stack_members(parts, list(range(21)))
    row = export_daily(ds, catalog(), '2026-09-06T06:00:00Z', input_sha256='0'*64, table=AnalyticTable())['entries'][1]
    assert row['status'] == 'degraded'
    assert row['ensemble']['valid_member_count'] == 20
    assert row['ensemble']['member_uvi'][0] is None
    assert row['ensemble']['member_valid_cells'][0] == 0
    assert row['support_uvi_range'][1] < 6
