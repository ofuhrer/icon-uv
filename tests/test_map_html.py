"""The static map loads separate, mutually consistent data products."""
import importlib.util
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
import pytest


spec = importlib.util.spec_from_file_location(
    'map_renderer', Path(__file__).resolve().parents[1] / 'examples/map/render.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_catalog_text_cannot_escape_data_script_or_expand_template_tokens():
    label = '</script><script>alert(1)</script> & __LEAFLET_JS__ \u2028'
    payload = {'locations': label, 'basemap': 'basemap.json', 'fields': None}
    html = renderer.render(payload)
    embedded = re.search(r'id="data-urls">(.*?)</script>', html, re.S).group(1)
    assert json.loads(embedded) == payload
    assert '<script>alert(1)</script>' not in html
    assert '\\u003c/script\\u003e' in embedded
    assert '__LEAFLET_JS__' in embedded
    assert not re.search(r'<script[^>]+src=', html)
    assert 'sourceMappingURL=' not in html


def test_bundled_snapshot_is_complete_and_page_matches_template_and_json():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/map/index.locations.json').read_text())
    schema = json.loads((root / 'icon_uv/data/daily-uv-v2.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload['example_snapshot'] is True
    assert len(payload['valid_dates']) == 4
    catalog = json.loads((root / 'examples/map/locations.json').read_text())
    ids = {e['id'] for e in catalog['entries']}
    assert len(payload['entries']) == 4*len(ids)
    for day, date in enumerate(payload['valid_dates']):
        rows = [r for r in payload['entries'] if r['valid_date'] == date]
        assert len(rows) == len(ids) and {r['location']['id'] for r in rows} == ids
        assert all(r['day'] == day for r in rows)
        assert all(r['status'] == 'ok' and r['display_uvi'] is not None for r in rows if r['location']['id'] != 'zermatt')
        unavailable = [r for r in rows if r['location']['id'] == 'zermatt']
        assert len(unavailable) == 1 and unavailable[0]['display_uvi'] is None
        assert 'insufficient_native_support' in unavailable[0]['reasons']
    html = (root / 'examples/map/index.html').read_text()
    urls = json.loads(re.search(r'id="data-urls">(.*?)</script>', html, re.S).group(1))
    assert urls == {kind: f'index.{kind}.json' for kind in ('locations', 'fields', 'basemap')}
    tiles = json.loads((root / 'examples/map' / urls['basemap']).read_text())
    assert tiles['images'] and all(s.startswith('data:image/png;base64,') for s in tiles['images'].values())
    fields = json.loads((root / 'examples/map' / urls['fields']).read_text())
    assert len(fields['days']) == 4
    assert all(d[mode].startswith('data:image/png;base64,') for d in fields['days'] for mode in ('forecast', 'clear_sky'))
    renderer.validate_products(payload, fields)
    assert renderer.render(urls) == html
    assert 'data:image/png;base64,' not in html
    assert payload['input_sha256'] not in html


@pytest.mark.parametrize('key', ['input_sha256', 'radiation_table_sha256', 'peak_definition', 'issued_at'])
def test_renderer_rejects_mixed_field_and_location_sources(key):
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/map/index.locations.json').read_text())
    fields = json.loads((root / 'examples/map/index.fields.json').read_text())
    fields[key] = '2026-09-08T06:00:00Z' if key == 'issued_at' else 'different'
    with pytest.raises(ValueError, match='mismatch'):
        renderer.validate_products(payload, fields)


def test_forecasts_can_refresh_without_rebuilding_html(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / 'source.json'
    payload = json.loads((root / 'examples/map/index.locations.json').read_text())
    source.write_text(json.dumps(payload))
    field_path = root / 'examples/map/index.fields.json'
    tiles = {'images': {}, 'zoom': 9, 'bounds': [[45, 5], [48, 11]]}
    monkeypatch.setattr(renderer, 'basemap', lambda _: tiles)
    output = tmp_path / 'out' / 'uv map.html'
    urls = renderer.write_bundle(source, field_path, output, tmp_path / 'cache')
    original = output.read_bytes()
    original_mtime = output.stat().st_mtime_ns
    assert urls['locations'] == 'uv%20map.locations.json'
    assert json.loads(output.with_suffix('.basemap.json').read_text()) == tiles
    # Catalog wording can change independently of the paired scientific products.
    payload['entries'][0]['location']['label'] = 'Updated example location'
    source.write_text(json.dumps(payload))
    renderer.write_bundle(source, field_path, output, tmp_path / 'cache')
    assert output.read_bytes() == original
    assert output.stat().st_mtime_ns == original_mtime
    assert json.loads(output.with_suffix('.locations.json').read_text()) == payload
    location_only = renderer.write_bundle(source, None, tmp_path / 'locations.html', tmp_path / 'cache')
    assert location_only['fields'] is None


def test_invalid_pair_is_rejected_before_writing_bundle(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/map/index.locations.json').read_text())
    payload['input_sha256'] = 'wrong'
    source = tmp_path / 'source.json'
    source.write_text(json.dumps(payload))
    def unexpected_download(_):
        pytest.fail('Must validate before retrieving basemap tiles')
    monkeypatch.setattr(renderer, 'basemap', unexpected_download)
    output = tmp_path / 'out' / 'map.html'
    with pytest.raises(ValueError, match='mismatch'):
        renderer.write_bundle(source, root / 'examples/map/index.fields.json', output, tmp_path / 'cache')
    assert not output.parent.exists()


def run_map_helpers(script):
    """Exercise the browser's presentation and numeric decoding without a DOM server."""
    import shutil
    import subprocess

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is needed for the map JavaScript regression checks')
    template = (Path(__file__).resolve().parents[1] / 'examples/map/template.html').read_text()
    helpers = template.rsplit('<script>', 1)[1].split('async function start(){', 1)[0]
    # Text-only DOM: assigning textContent cannot accidentally parse catalog HTML.
    dom = '''
class Element {
  constructor() { this.children=[]; this.dataset={}; this.style={}; this.attributes={};
    this.classList={add: name => this.className+=' '+name}; }
  append(...children) { this.children.push(...children); }
  setAttribute(name,value) { this.attributes[name]=value; }
  set textContent(value) { this.text=String(value); }
  get textContent() { return (this.text||'')+this.children.map(c=>c.textContent).join(' '); }
}
const document={createElement:()=>new Element(),querySelectorAll:()=>[]};
'''
    result = subprocess.run([node], input=dom+helpers+script, text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def test_map_popups_expose_available_degraded_support_and_ensemble_spread():
    result = run_map_helpers('''
const row={location:{label:'<img src=x onerror=alert(1)>',kind:'town',altitude_m:400},
  valid_date:'2026-09-07',status:'degraded',display_uvi:6,uvi:5.6,category:'high',
  reasons:['partial_ensemble_support','partial_spatial_support'],
  ensemble:{valid_member_count:20,p10:4.5,p90:7.2}};
const forecast={ensemble:{member_count:20,requested_member_ids:Array.from({length:21},(_,i)=>i)}};
const popup=details([row],forecast),badge=tile(row);
console.log(JSON.stringify({text:popup.textContent,title:badge.title,classes:badge.className,
  aria:badge.attributes['aria-label'],heading:popup.children[0].textContent,
  missing:details([{...row,display_uvi:null,uvi:null,status:'unavailable'}],forecast).textContent}));
''')
    assert 'UV Index 5.6' in result['text']
    assert '20 of 21 contributing members' in result['text']
    assert 'P10–P90: 4.5–7.2' in result['text']
    assert 'Some ensemble members are unavailable.' in result['text']
    assert 'Some regional cells have missing data.' in result['text']
    assert 'Limited forecast support.' in result['text']
    assert result['heading'] == '<img src=x onerror=alert(1)>'
    assert 'degraded' in result['classes'].split()
    assert 'limited support' in result['title']
    assert result['aria'] == result['title']
    assert 'Forecast unavailable.' in result['missing']
    assert 'Some ensemble members are unavailable.' in result['missing']


def test_map_raster_inspection_preserves_zero_missing_counts_and_mercator_position():
    result = run_map_helpers('''
const geometry={width:2,height:2,bounds:[[0,0],[80,2]]};
const field={pixels:new Uint8ClampedArray([0,0,0,255, 2,113,0,255, 9,255,0,0, 3,32,0,255]),
  counts:new Uint8ClampedArray([8,52,0,255, 7,208,0,255, 0,0,0,255, 7,108,0,255])};
console.log(JSON.stringify({
  zero:sampleField(field,geometry,{lat:80,lng:0}),
  rounded:sampleField(field,geometry,{lat:80,lng:2}),
  missing:sampleField(field,geometry,{lat:50,lng:0}),
  bottom:sampleField(field,geometry,{lat:0,lng:2}),
  outside:sampleField(field,geometry,{lat:81,lng:1}),
  single:sampleField({...field,counts:null},geometry,{lat:80,lng:0})}));
''')
    assert result['zero'] == {'uvi': 0, 'members': 21}
    assert result['rounded'] == {'uvi': 6.25, 'members': 20}
    assert result['missing'] == {'uvi': None, 'members': 0}
    assert result['bottom'] == {'uvi': 8, 'members': 19}
    assert result['outside'] is None
    assert result['single'] == {'uvi': 0, 'members': None}


def test_map_v4_geometry_matches_fields_or_requires_location_only():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/map/index.locations.json').read_text())
    fields = json.loads((root / 'examples/map/index.fields.json').read_text())
    payload.update(schema_version='daily-uv-v4', uv_geometry='ambient_horizontal')
    renderer.validate_products(payload, fields)
    payload['uv_geometry'] = 'terrain_screened'
    renderer.validate_products(payload)
    with pytest.raises(ValueError, match='UV geometry mismatch'):
        renderer.validate_products(payload, fields)
    payload.pop('uv_geometry')
    with pytest.raises(ValueError, match='UV geometry'):
        renderer.validate_products(payload)
    result = run_map_helpers('''
const f={schema_version:'daily-uv-v4',uv_geometry:'terrain_screened',entries:[{}]};
validateProducts(f,null);
try{validateProducts(f,{})}catch(error){console.log(JSON.stringify(error.message));}
''')
    assert 'UV geometry differ' in result


def test_shared_map_points_group_by_id_and_fallback_labels_remain_safe():
    result = run_map_helpers('''
const row=(kind,id,label)=>({location:{kind,id,label,altitude_m:1000},valid_date:'2026-09-07',
  display_uvi:null,uvi:null,reasons:[],status:'unavailable'});
const rows=[row('point','one','Same label'),row('point','two','Same label'),
  row('town','three','Same label'),row('region_altitude','r1','Same label'),
  row('region_altitude','r2','Same label'),row('point','<safe id>',undefined)];
const groups=groupLocations(rows);
console.log(JSON.stringify({sizes:[...groups.values()].map(group=>group.length),
  text:details([rows.at(-1)],{uv_geometry:'terrain_screened'}).textContent,
  screened:details([{...rows[0],location:{...rows[0].location,treatment:'adjusted'}}],
    {uv_geometry:'terrain_screened'}).textContent}));
''')
    assert result['sizes'] == [1, 1, 1, 2, 1]
    assert '<safe id>' in result['text']
    assert 'Native model surface · open horizon.' in result['text']
    assert 'Terrain-screened point UV · horizon screening proxy.' in result['screened']
