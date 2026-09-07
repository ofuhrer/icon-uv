"""The authoritative contract covers every supported calculation/publication path."""
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest
import xarray as xr

from icon_uv import PointLocation, RegionBand, compute_daily, export_daily_file, write_daily_json
from icon_uv.daily import daily_payload, export_daily
from icon_uv.data import file_sha256, write_netcdf
from icon_uv.schema import CONTRACT_SHA256, load_schema, validate_daily
from test_daily import AnalyticTable, grid
from test_ensemble import stack_members

ROOT = Path(__file__).resolve().parents[1]


def load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_is_valid_independent_and_identified_by_content():
    schema = load_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema['properties']['schema']['const'] == 'daily-uv'
    assert CONTRACT_SHA256 == hashlib.sha256((ROOT/'icon_uv/data/daily-uv.schema.json').read_bytes()).hexdigest()
    schema['properties'].clear()
    assert load_schema()['properties']


def test_offline_saved_input_example_uses_real_table(tmp_path):
    example = load_script(ROOT / 'examples/offline.py')
    payload = example.run(tmp_path)
    validate_daily(payload)
    assert len(payload['entries']) == 2
    assert all(entry['status'] == 'ok' and 0 < entry['uvi'] < 20 for entry in payload['entries'])
    with xr.open_dataset(tmp_path / 'uv.nc') as grid:
        assert grid.sizes == {'time': 48, 'cell': 1, 'bounds': 2}
        assert 'SYNTHETIC' in grid.attrs['title']
        assert grid.uvi.max() > 0
        assert len(grid.attrs['radiation_table_sha256']) == 64
    with pytest.raises(jsonschema.ValidationError):
        validate_daily({**payload, 'issued_at': 'not-a-date'})


@pytest.mark.parametrize('ensemble', [False, True])
@pytest.mark.parametrize('selection', [{}, {'days': 3}, {'days': 'all'}, {'dates': ['2026-09-06', '2026-09-08']}])
@pytest.mark.parametrize('kind', ['region', 'native', 'adjusted', 'screened', 'unsupported'])
def test_file_and_memory_publication_have_one_contract(tmp_path, ensemble, selection, kind):
    """Catalog kind, ensemble shape and date selection cannot change the schema."""
    table = AnalyticTable(); table.sha256 = 'a'*64
    ds = grid().assign_coords(cell=[60, 50, 40, 30, 20, 10])
    ds.attrs['radiation_table_sha256'] = table.sha256
    if ensemble:
        ds = stack_members([ds, ds], [0, 1])
    location = {
        'region': RegionBand('region', (9.7,46.7,9.9,46.9), 1000),
        'native': PointLocation('native',46.8,9.8,1000,treatment='native'),
        'adjusted': PointLocation('adjusted',46.8,9.8,1500),
        'screened': PointLocation('screened',46.8,9.8,1500,horizon_degrees=(15.,)*4),
        'unsupported': PointLocation('unsupported',45,6,1000),
    }[kind]
    path = tmp_path/'grid.nc'; write_netcdf(ds, path)
    issue = '2026-09-06T06:00:00Z'
    options = dict(table=table, terrain_screened=kind=='screened', **selection)
    file_result = export_daily_file(path, [location], issue, output=tmp_path/'file.json', **options)
    memory_result = export_daily(ds, [location], issue, input_sha256=file_sha256(path), **options)
    result = compute_daily(ds, [location], file_result['valid_dates'], table,
                           terrain_screened=kind=='screened')
    written = write_daily_json(result, tmp_path/'result.json', issue, input_sha256=file_sha256(path))
    assert file_result == memory_result == written == json.loads((tmp_path/'file.json').read_text())
    assert written['schema'] == 'daily-uv'
    assert written['contract_sha256'] == CONTRACT_SHA256
    validate_daily(written)


@pytest.mark.parametrize('ensemble', [False, True])
def test_inherited_albedo_and_required_point_metadata(ensemble):
    table = AnalyticTable(); table.sha256 = 'a'*64
    ds = grid(); ds.attrs['radiation_table_sha256'] = table.sha256
    if ensemble:
        ds = stack_members([ds, ds], [0,1])
    result = compute_daily(ds, [PointLocation('site',46.8,9.8,1000)], ['2026-09-06'], table)
    payload = daily_payload(result, '2026-09-06T06:00:00Z', input_sha256='0'*64)
    assert 'uv_albedo' not in payload['entries'][0]['location']
    validate_daily(payload)
    key = 'ensemble' if ensemble else 'peak_window_start_utc'
    del payload['entries'][0][key]
    with pytest.raises(jsonschema.ValidationError):
        validate_daily(payload)


def test_dates_and_days_are_mutually_exclusive_before_publication(tmp_path):
    table = AnalyticTable()
    output = tmp_path/'daily.json'; output.write_text('{"previous": true}')
    path = tmp_path/'grid.nc'; write_netcdf(grid(), path)
    with pytest.raises(ValueError, match='mutually exclusive'):
        export_daily_file(path, [PointLocation('site',46.8,9.8,1000)], '2026-09-06T06:00:00Z',
                          days=2, dates=['2026-09-06'], table=table, output=output)
    assert json.loads(output.read_text()) == {'previous': True}
