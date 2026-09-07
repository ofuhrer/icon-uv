"""Member identity, nonlinear processing order and daily ensemble contracts."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from jsonschema import Draft202012Validator, FormatChecker

from icon_uv import data
from icon_uv.daily import daily_cells, export_daily
from icon_uv.ensemble import member_ids, summary
from icon_uv.products import compute_grid, compute_pois, POI
from test_daily import grid, catalog, AnalyticTable
from test_uv import icon, cams, table


def stack_members(parts, ids):
    varying = [k for k, v in parts[0].data_vars.items() if 'time' in v.dims and k != 'time_bounds']
    result = xr.concat(parts, dim=xr.IndexVariable('member', ids), data_vars=varying,
                       coords='minimal', compat='equals', join='exact')
    result.attrs['ensemble_members'] = json.dumps(ids)
    return result


@pytest.fixture
def icon_service(monkeypatch):
    calls = []
    state = {'fault': None}
    def request(url, body=None):
        if url.endswith('/assets'):
            return SimpleNamespace(json=lambda: {'assets': [{'id':'horizontal-grid','href':'static'}]})
        if url == 'static':
            return SimpleNamespace(content=b'static')
        if body is not None:
            calls.append(body)
            return SimpleNamespace(json=lambda: {'features':[{'assets':{'data':{'href':json.dumps(body)}},
                                                                 'links':[{'rel':'self','href':'public-source'}]}]})
        return SimpleNamespace(content=url.encode())
    def decode(raw):
        if raw == b'static':
            return [(dict(shortName=name,units=unit,uuidOfHGrid='grid'),np.array(values),None)
                    for name,unit,values in [('h','m',[900,1000]),('tlat','degree',[46.8,46.9]),('tlon','degree',[9.8,9.9])]]
        body=json.loads(raw); var=body['forecast:variable'];lead=int(body['forecast:horizon'][4:6])
        ids=list(range(20,0,-1)) if body['forecast:perturbed'] else [0]
        # Provider order differs between leads.
        if lead % 2:ids.reverse()
        if body['forecast:perturbed'] and state['fault']=='missing':ids.pop()
        if body['forecast:perturbed'] and state['fault']=='duplicate':ids[-1]=ids[0]
        if state['fault']=='all_missing':ids=[]
        if state['fault']=='two_members':ids=[m for m in ids if m<2]
        if state['fault']=='three_members':ids=[m for m in ids if m<3]
        if state['fault']=='eighteen_members':ids=[m for m in ids if m<18]
        if state['fault']=='nineteen_members':ids=[m for m in ids if m<19]
        messages=[]
        for member in ids:
            meta=dict(shortName=var,units={'ASOD_S':'W m**-2','PS':'Pa','ALB_RAD':'%','SNOWC':'%'}[var],
                      perturbationNumber=member,uuidOfHGrid='grid',dataDate=20260907,dataTime=0,endStep=lead,
                      stepUnits=1,stepType='avg' if var=='ASOD_S' else 'instant',startStep=0,packingError=0)
            if state['fault']=='wrong_grid' and member==7:meta['uuidOfHGrid']='other'
            val={'ASOD_S':100+member,'PS':90000+member,'ALB_RAD':15,'SNOWC':0}[var]
            messages.append((meta,np.full(2,val,dtype=float),None))
        return messages
    monkeypatch.setattr(data,'_request',request)
    monkeypatch.setattr(data,'_decode_bytes',decode)
    return calls,state


def test_fetch_default_joins_all_21_members_by_id(icon_service):
    ds=data.fetch_icon('2026-09-07T00:00:00Z',1,3)
    assert ds.sw_down.dims==('member','time','cell')
    assert ds.sw_down.attrs['source_variable']=='ASOD_S'
    assert ds.sw_down.attrs['radiation_geometry']=='horizontal_without_orographic_shading'
    assert {c['forecast:variable'] for c in icon_service[0]}=={'ASOD_S','PS','ALB_RAD','SNOWC'}
    assert ds.member.values.tolist()==list(range(21))
    np.testing.assert_array_equal(ds.sw_down[:,0,0],np.arange(21)+100)
    assert ds.time_bounds.dims==('time','bounds')
    assert len(json.loads(ds.attrs['icon_sources']))==25
    assert {c['forecast:perturbed'] for c in icon_service[0]}=={False,True}
    control=data.fetch_icon('2026-09-07T00:00:00Z',1,3,ensemble=False)
    assert 'member' not in control.dims and control.attrs['member']==0
    np.testing.assert_array_equal(control.sw_down,ds.sw_down.sel(member=0))


@pytest.mark.parametrize('fault',['missing','duplicate','wrong_grid'])
def test_fetch_marks_incomplete_or_mixed_members_missing(icon_service,fault):
    icon_service[1]['fault']=fault
    result=data.fetch_icon('2026-09-07T00:00:00Z',1,3)
    assert np.isnan(result.sw_down).any()
    assert result.attrs['input_coverage_fraction'] >= .9


def test_memberwise_uv_and_pois_match_independent_calculations(icon,cams,table,tmp_path):
    parts=[icon.copy(deep=True) for _ in range(3)]
    for part,sw in zip(parts,[80,240,500]):part.sw_down.values[:]=sw
    ensemble=stack_members(parts,[0,1,2])
    expected=[compute_grid(p,cams,table) for p in parts]
    result=compute_grid(ensemble,cams,table)
    assert result.uvi.dims==('member','time','cell')
    assert result.time_bounds.dims==('time','bounds')
    for m in range(3):
        np.testing.assert_allclose(result.uvi.sel(member=m),expected[m].uvi)
    # Nonlinear cloud inversion must not be applied to averaged SW.
    shortcut=compute_grid(ensemble.mean('member',keep_attrs=True),cams,table)
    assert np.max(abs(result.uvi.mean('member')-shortcut.uvi))>.01
    pois=[POI('test',46.8,7,500,[0]*4,.05)]
    points=compute_pois(result,pois,table)
    for m in range(3):
        np.testing.assert_allclose(points.uvi.sel(member=m),compute_pois(expected[m],pois,table).uvi)
    path=tmp_path/'ensemble.nc';data.write_netcdf(result,path)
    with xr.open_dataset(path) as saved:
        assert member_ids(saved)==[0,1,2]
        np.testing.assert_allclose(saved.uvi,result.uvi)
    partial=compute_grid(ensemble.isel(member=[0,1]),cams,table)
    assert partial.sizes['member']==2


def test_daily_peak_precedes_ensemble_reduction():
    parts=[grid() for _ in range(3)]
    for p,h,scale in zip(parts,[10,12,14],[1,1.4,1.8]):
        p.cloud_scale.values[:]=.2
        p.cloud_scale.values[p.time.dt.hour.values==h]=scale
    ens=stack_members(parts,[0,1,2]);table=AnalyticTable()
    result=daily_cells(ens,'2026-09-06',table)
    peaks=np.stack([daily_cells(p,'2026-09-06',table)['uvi'] for p in parts])
    np.testing.assert_allclose(result['uvi'],np.median(peaks,axis=0))
    shortcut=ens.median('member',keep_attrs=True)
    assert np.all(result['uvi']>3*daily_cells(shortcut,'2026-09-06',table)['uvi'])
    assert np.all(result['member_uvi']==peaks)


def test_region_spatial_percentile_precedes_ensemble_reduction():
    parts=[grid() for _ in range(3)]
    for i,p in enumerate(parts):
        p.cloud_scale.values[:]=.2
        p.cloud_scale.values[:,2*i:2*i+2]=1
    table=AnalyticTable();table.sha256=hashlib.sha256(b'analytic fixture').hexdigest()
    for p in parts:p.attrs['radiation_table_sha256']=table.sha256
    ens=stack_members(parts,[0,1,2])
    c=catalog()
    for e in c['entries']:e['label']=e['id']
    payload=export_daily(ens,c,'2026-09-06T06:00:00Z',input_sha256='0'*64,table=table)
    assert payload['schema_version']=='daily-uv-v3' and len(payload['valid_dates'])==2
    region=payload['entries'][1]
    peak=daily_cells(parts[0],'2026-09-06',table)['uvi'].max()
    assert region['uvi']==pytest.approx(peak)
    assert payload['entries'][0]['uvi']==pytest.approx(peak*.2)
    assert 'peak_window_start_utc' not in payload['entries'][0]
    assert region['ensemble']['member_uvi']==pytest.approx([peak]*3)
    schema=json.loads((Path(__file__).parents[1]/'icon_uv/data/daily-uv-v3.schema.json').read_text())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(payload)
    partial=ens.isel(time=ens.time.dt.hour.values!=12)
    unavailable=export_daily(partial,catalog(),'2026-09-06T06:00:00Z',input_sha256='0'*64,table=table)
    assert all(r['uvi'] is None for r in unavailable['entries'])
    with pytest.raises(ValueError,match='quantile'):
        daily_cells(ens,'2026-09-06',table,ensemble_quantile=1.1)


def test_uncertainty_uses_unrounded_thresholds_and_custom_quantile():
    stats=summary([2.8,3.1,8.2])
    assert stats['probability_uvi_ge']=={'3':2/3,'6':1/3,'8':1/3,'11':0}
    parts=[grid() for _ in range(3)]
    for p,scale in zip(parts,[.2,.5,1]):p.cloud_scale.values[:]=scale
    ens=stack_members(parts,[0,1,2])
    payload=export_daily(ens,catalog(),'2026-09-06T06:00:00Z',input_sha256='0'*64,
                         table=AnalyticTable(),ensemble_quantile=.75)
    row=payload['entries'][0]
    assert row['uvi']==pytest.approx(np.quantile(row['ensemble']['member_uvi'],.75))
    assert payload['ensemble']['deterministic_quantile']==.75


def test_cli_ensemble_default_and_control_option(monkeypatch,tmp_path):
    from icon_uv import cli
    calls=[]
    monkeypatch.setattr(cli,'fetch_icon',lambda *a,**kw:calls.append(kw) or xr.Dataset())
    monkeypatch.setattr(cli,'write_netcdf',lambda *a:None)
    base=['icon-uv','fetch-icon','--reference','2026-09-07T00:00Z','--first-lead','1','--last-lead','3','--output',str(tmp_path/'out.nc')]
    for extra in [[],['--control'],['--ensemble']]:
        monkeypatch.setattr('sys.argv',base+extra);cli.main()
    assert [c['ensemble'] for c in calls]==[True,False,True]
    assert all(c['minimum_member_fraction']==.9 for c in calls)


@pytest.mark.parametrize('fault,works',[('all_missing',False),('eighteen_members',False),('nineteen_members',True)])
def test_fetch_minimum_ninety_percent_boundary(icon_service,fault,works):
    icon_service[1]['fault']=fault
    if works:
        result=data.fetch_icon('2026-09-07T00:00:00Z',1,3)
        assert result.attrs['input_coverage_fraction']==pytest.approx(19/21)
    else:
        with pytest.raises(ValueError,match='available'):
            data.fetch_icon('2026-09-07T00:00:00Z',1,3)


def test_missing_input_is_local_to_member_cell_and_hour(icon,cams,table):
    parts=[icon.copy(deep=True) for _ in range(3)]
    parts[1].sw_down.values[0,0]=np.nan
    ens=stack_members(parts,[0,1,2]);ens.attrs['minimum_member_fraction']=.1
    result=compute_grid(ens,cams,table)
    assert np.isnan(result.uvi.sel(member=1)[0,0])
    assert int(result.quality_flag.sel(member=1)[0,0]) & 128
    assert np.isfinite(result.uvi.sel(member=1)[1,0])
    assert np.isfinite(result.uvi.sel(member=0)).all()
    points=compute_pois(result,[POI('test',46.8,7,500,[0]*4,.05)],table)
    assert np.isnan(points.uvi.sel(member=1)[0,0])
    assert np.isfinite(points.uvi.sel(member=1)[1,0])


def test_daily_excludes_incomplete_members_and_marks_low_support():
    parts=[grid(n=1) for _ in range(21)]
    for p in parts[19:]:
        p.effective_cloud_tau550.values[p.time.dt.hour.values==12]=np.nan
    ens=stack_members(parts,list(range(21)))
    table=AnalyticTable()
    result=daily_cells(ens,'2026-09-06',table)
    assert result['available'][0] and result['member_count'][0]==19
    payload=export_daily(ens,catalog(),'2026-09-06T06:00:00Z',input_sha256='0'*64,table=table)
    row=payload['entries'][0]
    assert row['status']=='degraded' and 'partial_ensemble_support' in row['reasons']
    assert row['ensemble']['valid_member_count']==19
    assert row['ensemble']['member_uvi'][19:] == [None]*2
    assert all('NaT' not in t for t in row['peak_window_start_range_utc'])
    ens.effective_cloud_tau550.values[18,ens.time.dt.hour.values==12,:]=np.nan
    assert not daily_cells(ens,'2026-09-06',table)['available'][0]
    ens.attrs['minimum_member_fraction']=.8
    assert daily_cells(ens,'2026-09-06',table)['available'][0]


def test_fetch_minimum_fraction_is_configurable(icon_service):
    icon_service[1]['fault']='three_members'
    with pytest.raises(ValueError,match='available'):
        data.fetch_icon('2026-09-07T00:00:00Z',1,3)
    result=data.fetch_icon('2026-09-07T00:00:00Z',1,3,minimum_member_fraction=.1)
    assert result.attrs['input_coverage_fraction']==pytest.approx(3/21)


def test_map_rasters_keep_coverage_and_reject_mismatched_reductions(monkeypatch):
    from test_map_fields import fields, decode
    from test_map_html import renderer
    parts=[grid(n=2) for _ in range(21)]
    for p in parts[19:]:
        p.effective_cloud_tau550.values[p.time.dt.hour.values==12,:]=np.nan
    parts[18].effective_cloud_tau550.values[parts[18].time.dt.hour.values==12,1]=np.nan
    ens=stack_members(parts,list(range(21)))
    monkeypatch.setattr(fields,'raster_support',lambda *a,**kw:(np.array([0,1]),np.array([True,True]),
                        dict(width=2,height=1,bounds=[[46,9],[47,10]])))
    monkeypatch.setattr(fields,'daily_cells',lambda *a,**kw:daily_cells(*a,table=AnalyticTable(),**kw))
    raster=fields.export_fields(ens,'2026-09-06T06:00:00Z','0'*64)
    np.testing.assert_array_equal(decode(raster['days'][0]['forecast_member_count']),[[19,18]])
    values=decode(raster['days'][0]['forecast'])
    assert np.isfinite(values[0,0]) and np.isnan(values[0,1])
    payload=export_daily(ens,catalog(),'2026-09-06T06:00:00Z',input_sha256='0'*64,table=AnalyticTable(),days=4)
    renderer.validate_products(payload,raster)
    for key,value in [('deterministic_quantile',.75),('minimum_member_fraction',.8)]:
        changed=dict(raster,ensemble=dict(raster['ensemble'],**{key:value}))
        with pytest.raises(ValueError,match='ensemble definition mismatch'):
            renderer.validate_products(payload,changed)


def test_integrity_check_accepts_flagged_missing_inputs_only(icon,cams,table):
    from icon_uv.check_grid import check_grid
    icon.attrs['bbox']=json.dumps([6,46,8,48])
    ens=stack_members([icon.copy(deep=True) for _ in range(3)],[0,1,2])
    ens.sw_down.values[1,0,0]=np.nan
    result=compute_grid(ens,cams,table)
    report=check_grid(result,table,cells=1)
    assert report['passed'] and report['members']['1']['missing_cell_hours']==1
    result.uvi.values[0,0,0]=np.nan
    with pytest.raises(ValueError,match='Invalid output uvi'):
        check_grid(result,table,cells=1)
