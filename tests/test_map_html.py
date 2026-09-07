"""The standalone renderer must embed data without creating executable markup."""
import importlib.util
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker


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
    assert len(payload['entries']) == 144
    for day, date in enumerate(payload['valid_dates']):
        rows = [r for r in payload['entries'] if r['valid_date'] == date]
        assert len(rows) == 36
        assert all(r['day'] == day and r['status'] == 'ok' and r['display_uvi'] is not None for r in rows)
    html = (root / 'examples/meteoswiss_map.html').read_text()
    embedded = json.loads(re.search(r'id="forecast">(.*?)</script>', html, re.S).group(1))
    tiles = json.loads(re.search(r'id="basemap">(.*?)</script>', html, re.S).group(1))
    assert embedded == payload
    assert tiles['images'] and all(s.startswith('data:image/png;base64,') for s in tiles['images'].values())
    assert renderer.render(payload, tiles) == html
