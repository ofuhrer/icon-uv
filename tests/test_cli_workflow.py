"""Exercise the public shared catalog workflow through actual CLI parsing."""
import json
import sys
import pytest
from icon_uv.cli import main
from icon_uv.schema import validate_daily
from icon_uv.radiation import RadiationTable
from icon_uv.data import write_netcdf
from test_daily import grid


def fixture(tmp_path):
    ds=grid(n=1)
    ds.attrs.update(radiation_table_sha256=RadiationTable().sha256,solar_samples_per_hour=12)
    path=tmp_path/'grid.nc';write_netcdf(ds,path)
    cat=tmp_path/'locations.json'
    cat.write_text(json.dumps({'entries':[dict(kind='point',id='a',latitude=46.8,longitude=9.8,altitude_m=1000)]}))
    return path,cat


def invoke(monkeypatch,*args):
    monkeypatch.setattr(sys,'argv',['icon-uv',*map(str,args)])
    main()


def test_shared_cli_preflight_points_daily(monkeypatch,tmp_path,capsys):
    grid,catalog=fixture(tmp_path)
    invoke(monkeypatch,'preflight','--grid',grid,'--locations',catalog,'--issued-at','2026-09-06T06:00:00Z','--days','1')
    assert json.loads(capsys.readouterr().out)['ready']
    invoke(monkeypatch,'points','--grid',grid,'--locations',catalog,'--output',tmp_path/'points.nc')
    assert (tmp_path/'points.nc').exists()
    invoke(monkeypatch,'daily','--grid',grid,'--locations',catalog,'--issued-at','2026-09-06T06:00:00Z',
           '--dates','2026-09-06','2026-09-08','--output',tmp_path/'daily.json')
    payload=json.loads((tmp_path/'daily.json').read_text());validate_daily(payload)
    assert payload['valid_dates']==['2026-09-06','2026-09-08']
    assert payload['entries'][0]['status']=='ok'
    assert payload['entries'][1]['status']=='unavailable'


def test_cli_unready_and_actionable_errors(monkeypatch,tmp_path,capsys):
    grid,catalog=fixture(tmp_path)
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch,'preflight','--grid',grid,'--locations',catalog,'--issued-at','2026-09-06T06:00:00Z','--days','4')
    assert exc.value.code==1
    assert not json.loads(capsys.readouterr().out)['ready']
    with pytest.raises(SystemExit,match='icon-uv:'):
        invoke(monkeypatch,'points','--grid',tmp_path/'absent.nc','--locations',catalog,'--output',tmp_path/'points.nc')
