"""One location model drives hourly and daily products with explicit physics."""
import json
import numpy as np
import pytest
import xarray as xr
from icon_uv.locations import PointLocation, RegionBand, load_locations, plan_support
from icon_uv.products import compute_grid, compute_points, compute_pois, POI
from icon_uv.daily import compute_daily, export_daily, export_daily_file, write_daily_json
from icon_uv.data import write_netcdf
from icon_uv.schema import validate_daily
from test_daily import grid, AnalyticTable
from test_uv import icon, cams, table
from test_ensemble import stack_members


def native():
    return PointLocation('town', 46.8, 9.8, 1000, treatment='native')


def adjusted(horizon=(0.,)*4):
    return PointLocation('summit', 46.8, 9.8, 2000, treatment='adjusted', uv_albedo=.05, horizon_degrees=horizon)


def test_shared_catalog_roundtrip_and_legacy_adapters(tmp_path):
    path = tmp_path/'catalog.json'
    path.write_text(json.dumps({'catalog_version': 2, 'entries': [native().to_entry(), adjusted().to_entry(), RegionBand('alps', (9.7,46.7,9.9,46.9),1000).to_entry()]}))
    locations = load_locations(path)
    assert len(locations.locations) == 3
    assert len(locations.points) == 2
    assert locations.points[1].treatment == 'adjusted'
    legacy = load_locations([dict(name='davos', latitude=46.8, longitude=9.8, altitude_m=1500, uv_albedo=.05, horizon_degrees=[0]*4)])
    assert legacy.points[0].treatment == 'adjusted'
    with pytest.raises(ValueError, match='unique'):
        load_locations([native(), native()])
    with pytest.raises(ValueError, match='treatment'):
        load_locations([dict(native().to_entry(), treatment='implicit')])
    with pytest.raises(ValueError, match='Native'):
        PointLocation('town',46.8,9.8,1000,treatment='native',uv_albedo=.1)


def test_shared_native_hourly_matches_grid_and_legacy_point_unchanged(icon,cams,table):
    g = compute_grid(icon, cams, table)
    p = PointLocation('town',46.8,7,500,treatment='native')
    hourly = compute_points(g,[p],table)
    np.testing.assert_allclose(hourly.uvi[:,0],g.uvi[:,0],rtol=2e-6)
    assert hourly.terrain_screened_uvi.isnull().all()
    ap = PointLocation('local',46.8,7,900,treatment='adjusted',uv_albedo=.1,horizon_degrees=(10.,)*4)
    common = compute_points(g,[ap],table)
    old = compute_pois(g,[POI('local',46.8,7,900,(10.,)*4,.1)],table)
    xr.testing.assert_identical(common,old)
    assert (common.pressure_pa < g.pressure_pa.isel(cell=0)).all()


def test_adjusted_daily_uses_target_surface_and_rolling_support(tmp_path):
    ds=grid(); t=AnalyticTable();t.sha256='a'*64
    ds.attrs['radiation_table_sha256']=t.sha256
    locations=[native(), adjusted((90.,)*4)]
    ambient=compute_daily(ds,locations,['2026-09-06'],t)
    screened=compute_daily(ds,[locations[1]],['2026-09-06'],t,terrain_screened=True)
    assert ambient.entries[1]['uvi'] > 4
    assert screened.entries[0]['uvi'] == 0
    assert ambient.entries[1]['aggregation']=='adjusted_point_daily_maximum'
    assert ambient.entries[1]['source_point']['altitude_difference_m']==-1000
    for result in (ambient,screened):
        payload=write_daily_json(result,tmp_path/'daily.json','2026-09-06T06:00:00Z',input_sha256='0'*64)
        validate_daily(payload)
        assert payload['schema_version']=='daily-uv-v5'
    with pytest.raises(ValueError,match='horizon'):
        compute_daily(ds,locations,['2026-09-06'],t,terrain_screened=True)
    with pytest.raises(ValueError,match='horizon'):
        compute_daily(ds,[adjusted(None)],['2026-09-06'],t,terrain_screened=True)
    gap=ds.isel(time=ds.time.dt.hour.values!=12)
    unavailable=compute_daily(gap,[adjusted()],['2026-09-06'],t)
    assert unavailable.entries[0]['status']=='unavailable'


def test_daily_file_matches_memory_and_handles_unsupported_catalog(tmp_path):
    ds=grid();t=AnalyticTable(); t.sha256='a'*64
    ds.attrs['radiation_table_sha256']=t.sha256
    path=tmp_path/'grid.nc';write_netcdf(ds,path)
    result=export_daily_file(path,[native(),adjusted()],'2026-09-06T06:00:00Z',table=t,days=3)
    validate_daily(result)
    assert len(result['valid_dates'])==3
    assert result['entries'][-1]['status']=='unavailable'
    unsupported=export_daily_file(path,[PointLocation('far',45,5,0)],'2026-09-06T06:00:00Z',table=t,days='all')
    assert all(e['reasons']==['insufficient_native_support'] for e in unsupported['entries'])


def test_explicit_dates_and_member_products_share_schema(tmp_path):
    t=AnalyticTable();t.sha256='a'*64
    parts=[grid(n=1) for _ in range(3)]
    for i,p in enumerate(parts):
        p.attrs['radiation_table_sha256']=t.sha256
        p.cloud_scale.values[:]=i+1
    ds=stack_members(parts,[0,1,2])
    payload=export_daily(ds,[native(),adjusted()],'2026-09-06T06:00:00Z',table=t,input_sha256='0'*64,dates=['2026-09-06','2026-09-08'])
    validate_daily(payload)
    assert [e['day'] for e in payload['entries']]==[0,0,2,2]
    assert payload['entries'][0]['uvi']==pytest.approx(payload['entries'][0]['ensemble']['member_uvi'][1])
    for invalid in ([],['2026-09-07','2026-09-06'],['2026-09-06']*2):
        with pytest.raises(ValueError): compute_daily(ds,[native()],invalid,t)


def test_support_tie_uses_native_id():
    ds=grid(n=2).assign_coords(cell=[20,10])
    p=native()
    assert ds.cell.values[plan_support(ds,p).indices[0]]==10
    other=ds.isel(cell=[1,0])
    assert other.cell.values[plan_support(other,p).indices[0]]==10


def test_catalog_normalizes_points_and_isolated_metadata(tmp_path):
    original={'entries':[{'kind':'point','id':'a','latitude':46.8,'longitude':9.8,'altitude_m':1000}]}
    c=load_locations(original)
    original['entries'][0]['latitude']=0
    c.catalog['entries'][0]['longitude']=0
    assert c.catalog['entries'][0]['latitude']==46.8
    assert c.catalog['entries'][0]['longitude']==9.8
    assert c.catalog['entries'][0]['treatment']=='adjusted'
    t=AnalyticTable();t.sha256='a'*64
    ds=grid();ds.attrs['radiation_table_sha256']=t.sha256
    legacy=[dict(name='legacy',latitude=46.8,longitude=9.8,altitude_m=1000,uv_albedo=.05,horizon_degrees=[0]*4)]
    for locs in (c,legacy):
        result=compute_daily(ds,locs,['2026-09-06'],t)
        payload=write_daily_json(result,tmp_path/'daily.json','2026-09-06T06:00:00Z',input_sha256='0'*64)
        validate_daily(payload)


@pytest.mark.parametrize('source',[None,{'entries':None},{'entries':[None]},{'entries':['oops']}])
def test_malformed_catalog_is_actionable(source):
    with pytest.raises(ValueError): load_locations(source)


@pytest.mark.parametrize('distance',[True,False,float('nan'),float('inf'),-1])
def test_shared_distance_validation(distance):
    with pytest.raises(ValueError): PointLocation('a',46.8,9.8,1000,maximum_distance_km=distance)


@pytest.mark.parametrize('expected',[[],[0,0],[-1],[21],[True],{'0':0},'oops'])
def test_invalid_requested_member_identity(expected):
    from icon_uv.ensemble import required_members
    ds=stack_members([grid(n=1)],[0]);ds.attrs['ensemble_members']=json.dumps(expected)
    with pytest.raises(ValueError): required_members(ds)


def test_adjusted_rolling_peak_against_direct_five_minute_reference():
    from icon_uv.radiation import RadiationTable, solar_geometry
    from icon_uv.daily import local_day_bounds
    t=RadiationTable();ds=grid(n=1)
    ds.attrs.update(radiation_table_sha256=t.sha256,solar_samples_per_hour=12)
    ds.effective_cloud_tau550.values[:]=2
    ds.cloud_scale.values[:,0]=np.where(ds.time.dt.hour.values < 11,.7,1.)
    target=PointLocation('local',46.83,9.82,1800,treatment='adjusted',uv_albedo=.6,horizon_degrees=(15.,)*4)
    result=compute_daily(ds,[target],['2026-09-06'],t)
    start,end=local_day_bounds('2026-09-06')
    times=np.arange(start,end,np.timedelta64(5,'m'))+np.timedelta64(150,'s')
    z,az,distance=solar_geometry(times,target.latitude,target.longitude)
    pressure=90000*np.exp(-800/8434)
    components=t.at(z,300,pressure,.1,.6,2)[...,2:]
    hours=times.astype('datetime64[h]').astype('int64')%24
    values=40*components.sum(axis=-1)*distance*np.where(hours<11,.7,1.)
    reference=np.lib.stride_tricks.sliding_window_view(values,6).mean(axis=-1).max()
    hourly=compute_points(ds,[target],t).uvi.values[:,0]
    assert result.entries[0]['uvi']==pytest.approx(reference,rel=1e-12)
    assert result.entries[0]['uvi'] > hourly[:24].max()
    screened=40*(components[:,0]*(90-z>15)+components[:,1]*np.cos(np.deg2rad(15))**2)*distance*np.where(hours<11,.7,1.)
    expected_screened=np.lib.stride_tricks.sliding_window_view(screened,6).mean(axis=-1).max()
    assert compute_daily(ds,[target],['2026-09-06'],t,terrain_screened=True).entries[0]['uvi']==pytest.approx(expected_screened,rel=1e-12)


@pytest.mark.parametrize('key', ['latitude','longitude','altitude_m','uv_albedo'])
def test_boolean_physical_values_rejected(key):
    args=dict(id='a',latitude=46.8,longitude=9.8,altitude_m=1000,treatment='adjusted',uv_albedo=.05)
    args[key]=True
    with pytest.raises(ValueError,match='finite number'): PointLocation(**args)
    with pytest.raises(ValueError,match='finite number'): RegionBand('r',(True,46.,10.,47.),1000)


def test_default_point_support_adjusts_large_elevation_difference():
    """A valley town can use nearby model terrain without the native height filter."""
    from icon_uv.locations import prepare_point

    ds = grid(n=1)
    ds['altitude_m'] = ('cell', [2278.])
    ds['latitude'] = ('cell', [46.02])
    ds['longitude'] = ('cell', [7.75])
    point = PointLocation('zermatt', 46.0175, 7.7466, 1617)
    plan = plan_support(ds, point)
    assert plan.indices.tolist() == [0]
    local = prepare_point(ds, plan)
    np.testing.assert_allclose(local.pressure_pa, ds.pressure_pa * np.exp(661 / 8434))
    xr.testing.assert_identical(local.uv_albedo, ds.uv_albedo)
    assert local.altitude_m.item() == 1617
    legacy = load_locations([dict(kind='town', id='zermatt', latitude=point.latitude,
                                 longitude=point.longitude, altitude_m=point.altitude_m)])
    assert legacy.points[0].treatment == 'native'
    assert not len(plan_support(ds, legacy.points[0]).indices)


@pytest.mark.parametrize('ensemble', [False, True])
def test_point_inherits_time_and_member_varying_albedo(ensemble):
    from icon_uv.radiation import RadiationTable

    t = RadiationTable()
    parts = [grid(n=1) for _ in range(2 if ensemble else 1)]
    for member, ds in enumerate(parts):
        ds.attrs.update(radiation_table_sha256=t.sha256, solar_samples_per_hour=4)
        ds.uv_albedo.values[:, 0] = np.where(ds.time.dt.hour.values < 12, .05, .4) + member * .2
    ds = stack_members(parts, [0, 1]) if ensemble else parts[0]
    original = ds.copy(deep=True)
    point = PointLocation('ambient', 46.8, 9.8, 1000)
    override = PointLocation('measured', 46.8, 9.8, 1000, uv_albedo=.1)
    result = compute_points(ds, [point, override], t)
    expected_dims = ('member', 'time', 'poi') if ensemble else ('time', 'poi')
    assert result.uv_albedo.dims == expected_dims
    np.testing.assert_allclose(result.uv_albedo.sel(poi='ambient'), ds.uv_albedo.isel(cell=0))
    np.testing.assert_allclose(result.uv_albedo.sel(poi='measured'), .1)
    assert result.terrain_screened_uvi.isnull().all()
    if ensemble:
        # The inherited brighter surface affects UV, while the fixed override
        # gives identical member results when the atmospheric columns are equal.
        assert (result.uvi.sel(member=1, poi='ambient') > result.uvi.sel(member=0, poi='ambient')).any()
        np.testing.assert_allclose(result.uvi.sel(member=0, poi='measured'), result.uvi.sel(member=1, poi='measured'))
    fixed = compute_points(ds, [override], t)
    assert fixed.uv_albedo.dims == ('poi',)
    xr.testing.assert_identical(ds, original)


def test_daily_inherited_albedo_matches_explicit_surface():
    from icon_uv.radiation import RadiationTable

    t = RadiationTable()
    ds = grid(n=1)
    ds.attrs['radiation_table_sha256'] = t.sha256
    ds.uv_albedo.values[:] = .6
    inherited = PointLocation('inherited', 46.8, 9.8, 1800)
    explicit = PointLocation('explicit', 46.8, 9.8, 1800, uv_albedo=.6)
    dry = PointLocation('dry', 46.8, 9.8, 1800, uv_albedo=.05)
    result = compute_daily(ds, [inherited, explicit, dry], ['2026-09-06'], t)
    assert result.entries[0]['uvi'] == pytest.approx(result.entries[1]['uvi'])
    assert result.entries[0]['uvi'] > result.entries[2]['uvi']


def test_missing_inherited_albedo_excludes_member_daily_product():
    from icon_uv.daily import daily_payload
    from icon_uv.radiation import RadiationTable

    t = RadiationTable()
    parts = [grid(n=1) for _ in range(3)]
    for m, ds in enumerate(parts):
        ds.attrs.update(radiation_table_sha256=t.sha256, solar_samples_per_hour=4)
        ds.uv_albedo.values[:] = .05 + m * .2
    parts[2].uv_albedo.values[parts[2].time.dt.hour.values == 12, 0] = np.nan
    ds = stack_members(parts, [0, 1, 2])
    ds.attrs['minimum_member_fraction'] = .66
    point = PointLocation('fallback', 46.8, 9.8, 1800)
    hourly = compute_points(ds, [point], t).sel(member=2)
    noon = hourly.time.dt.hour.values == 12
    assert hourly.uvi.values[noon].shape[0] > 0
    assert np.isnan(hourly.uvi.values[noon]).all()
    assert np.all(hourly.quality_flag.values[noon] & 128)
    result = compute_daily(ds, [point], ['2026-09-06'], t)
    entry = result.entries[0]
    assert entry['status'] == 'degraded'
    assert entry['reasons'] == ['partial_ensemble_support']
    assert entry['ensemble']['valid_member_count'] == 2
    assert entry['ensemble']['member_uvi'][2] is None
    assert entry['uvi'] == pytest.approx(np.mean(entry['ensemble']['member_uvi'][:2]))
    validate_daily(daily_payload(result, '2026-09-06T06:00:00Z', input_sha256='0' * 64))
