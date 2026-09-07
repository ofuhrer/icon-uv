"""The static map loads separate, mutually consistent data products."""
import importlib.util
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
import pytest


spec = importlib.util.spec_from_file_location(
    'map_renderer', Path(__file__).resolve().parents[1] / 'examples/render_meteoswiss_map.py')
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
    payload = json.loads((root / 'examples/meteoswiss_map.locations.json').read_text())
    schema = json.loads((root / 'icon_uv/data/daily-uv-v2.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload['example_snapshot'] is True
    assert len(payload['valid_dates']) == 4
    catalog = json.loads((root / 'examples/meteoswiss_map_locations.json').read_text())
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
    html = (root / 'examples/meteoswiss_map.html').read_text()
    urls = json.loads(re.search(r'id="data-urls">(.*?)</script>', html, re.S).group(1))
    assert urls == {kind: f'meteoswiss_map.{kind}.json' for kind in ('locations', 'fields', 'basemap')}
    tiles = json.loads((root / 'examples' / urls['basemap']).read_text())
    assert tiles['images'] and all(s.startswith('data:image/png;base64,') for s in tiles['images'].values())
    fields = json.loads((root / 'examples' / urls['fields']).read_text())
    assert len(fields['days']) == 4
    assert all(d[mode].startswith('data:image/png;base64,') for d in fields['days'] for mode in ('forecast', 'clear_sky'))
    renderer.validate_products(payload, fields)
    assert renderer.render(urls) == html
    assert 'data:image/png;base64,' not in html
    assert payload['input_sha256'] not in html


@pytest.mark.parametrize('key', ['input_sha256', 'radiation_table_sha256', 'peak_definition', 'issued_at'])
def test_renderer_rejects_mixed_field_and_location_sources(key):
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/meteoswiss_map.locations.json').read_text())
    fields = json.loads((root / 'examples/meteoswiss_map.fields.json').read_text())
    fields[key] = '2026-09-08T06:00:00Z' if key == 'issued_at' else 'different'
    with pytest.raises(ValueError, match='mismatch'):
        renderer.validate_products(payload, fields)


def test_forecasts_can_refresh_without_rebuilding_html(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / 'source.json'
    payload = json.loads((root / 'examples/meteoswiss_map.locations.json').read_text())
    source.write_text(json.dumps(payload))
    field_path = root / 'examples/meteoswiss_map.fields.json'
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
    payload = json.loads((root / 'examples/meteoswiss_map.locations.json').read_text())
    payload['input_sha256'] = 'wrong'
    source = tmp_path / 'source.json'
    source.write_text(json.dumps(payload))
    def unexpected_download(_):
        pytest.fail('Must validate before retrieving basemap tiles')
    monkeypatch.setattr(renderer, 'basemap', unexpected_download)
    output = tmp_path / 'out' / 'map.html'
    with pytest.raises(ValueError, match='mismatch'):
        renderer.write_bundle(source, root / 'examples/meteoswiss_map.fields.json', output, tmp_path / 'cache')
    assert not output.parent.exists()
