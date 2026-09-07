"""The standalone renderer must embed data without creating executable markup."""
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
    payload = {'schema_version': 'daily-uv-v2', 'entries': [{'location': {'label': label}}]}
    html = renderer.render(payload, {'images': {}, 'zoom': 9, 'bounds': [[45,5],[48,11]]})
    embedded = re.search(r'id="forecast">(.*?)</script>', html, re.S).group(1)
    assert json.loads(embedded) == payload
    assert '<script>alert(1)</script>' not in html
    assert '\\u003c/script\\u003e' in embedded
    assert '__LEAFLET_JS__' in embedded
    assert not re.search(r'<script[^>]+src=', html)
    assert 'sourceMappingURL=' not in html


def test_bundled_snapshot_is_complete_and_page_matches_template_and_json():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/meteoswiss_map.sample.json').read_text())
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
    embedded = json.loads(re.search(r'id="forecast">(.*?)</script>', html, re.S).group(1))
    tiles = json.loads(re.search(r'id="basemap">(.*?)</script>', html, re.S).group(1))
    assert embedded == payload
    assert tiles['images'] and all(s.startswith('data:image/png;base64,') for s in tiles['images'].values())
    fields = json.loads((root / 'examples/meteoswiss_map.fields.json').read_text())
    embedded_fields = json.loads(re.search(r'id="fields">(.*?)</script>', html, re.S).group(1))
    assert fields == embedded_fields
    assert len(fields['days']) == 4
    assert all(d[mode].startswith('data:image/png;base64,') for d in fields['days'] for mode in ('forecast', 'clear_sky'))
    assert renderer.render(payload, tiles, fields) == html


@pytest.mark.parametrize('key', ['input_sha256', 'radiation_table_sha256', 'peak_definition', 'issued_at'])
def test_renderer_rejects_mixed_field_and_location_sources(key):
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'examples/meteoswiss_map.sample.json').read_text())
    fields = json.loads((root / 'examples/meteoswiss_map.fields.json').read_text())
    fields[key] = '2026-09-08T06:00:00Z' if key == 'issued_at' else 'different'
    with pytest.raises(ValueError, match='mismatch'):
        renderer.render(payload, {}, fields)
