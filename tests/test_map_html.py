"""The standalone renderer must embed data without creating executable markup."""
import importlib.util
import json
from pathlib import Path
import re


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
