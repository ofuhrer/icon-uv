"""Build one offline HTML page from the map example's JSON output."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
from datetime import datetime

import requests


def script_json(value):
    """Keep arbitrary catalog text inside its JSON script element."""
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            .replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def basemap(cache):
    """Embed swisstopo relief at zoom 9; Leaflet scales it for offline zooming."""
    zoom = 9
    west, south, east, north = 5.6, 45.6, 10.85, 47.95

    def tile(lon, lat):
        return (math.floor((lon + 180) / 360 * 2**zoom),
                math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2**zoom))

    x0, y1 = tile(west, south)
    x1, y0 = tile(east, north)
    cache.mkdir(parents=True, exist_ok=True)

    def get(pair):
        x, y = pair
        key = f'{zoom}/{x}/{y}'
        path = cache / f'relief-{zoom}-{x}-{y}.png'
        if not path.exists():
            url = ('https://wmts.geo.admin.ch/1.0.0/'
                   f'ch.swisstopo.leichte-basiskarte_reliefschattierung/default/current/3857/{key}.png')
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            if not response.content.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError(f'Expected a PNG tile: {url}')
            path.write_bytes(response.content)
        return key, 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()

    with ThreadPoolExecutor(max_workers=4) as pool:
        images = dict(pool.map(get, [(x, y) for x in range(x0, x1+1) for y in range(y0, y1+1)]))
    return dict(zoom=zoom, bounds=[[south, west], [north, east]], images=images)


def render(payload, tiles, fields=None):
    """Return a standalone document; dependencies and forecast data are inline."""
    if payload.get('schema_version') not in ('daily-uv-v1', 'daily-uv-v2') or not payload.get('entries'):
        raise ValueError('Expected a nonempty daily UV product')
    if fields is not None:
        if fields.get('schema_version') != 'uv-map-fields-v1' or fields.get('encoding') != 'png-rg-uvi-times-100-alpha-valid':
            raise ValueError('Unsupported map fields')
        for key in ('input_sha256', 'radiation_table_sha256', 'peak_definition'):
            if fields.get(key) != payload.get(key):
                raise ValueError(f'Field/location product mismatch: {key}')
        instant = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
        if instant(fields['issued_at']) != instant(payload['issued_at']):
            raise ValueError('Field/location issuance mismatch')
        if [d['valid_date'] for d in fields['days']] != sorted({r['valid_date'] for r in payload['entries']})[:4]:
            raise ValueError('Field/location dates mismatch')
    here = Path(__file__).parent
    template = (here / 'meteoswiss_map.template.html').read_text(encoding='utf-8')
    replacements = {
        '__LEAFLET_CSS__': (here / 'vendor/leaflet-1.9.4.css').read_text(),
        '__LEAFLET_JS__': (here / 'vendor/leaflet-1.9.4.js').read_text().split('//# sourceMappingURL=')[0],
        '__LEAFLET_LICENSE__': (here / 'vendor/leaflet-LICENSE').read_text(),
        '__FORECAST_JSON__': script_json(payload),
        '__TILES_JSON__': script_json(tiles),
        '__FIELDS_JSON__': script_json(fields),
    }
    # One pass prevents replacement tokens in catalog text from becoming markup.
    import re
    return re.sub('|'.join(map(re.escape, replacements)), lambda m: replacements[m[0]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).with_name('meteoswiss_map.sample.json'),
                        help='Daily UV JSON (default: bundled example snapshot)')
    parser.add_argument('--output', type=Path, default=Path('work/meteoswiss-map.html'))
    parser.add_argument('--fields', type=Path, help='Daily field JSON from meteoswiss_fields.py')
    parser.add_argument('--cache', type=Path, default=Path('work/swisstopo-relief-tiles'))
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Input JSON and output HTML must differ')
    payload = json.loads(args.input.read_text(encoding='utf-8'))
    field_path = args.fields
    if field_path is None and args.input.resolve() == Path(__file__).with_name('meteoswiss_map.sample.json').resolve():
        field_path = Path(__file__).with_name('meteoswiss_map.fields.json')
    fields = json.loads(field_path.read_text()) if field_path else None
    document = render(payload, basemap(args.cache), fields)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding='utf-8')
    print(f'{args.output} ({len(document.encode()) / 1024 / 1024:.2f} MiB, self-contained)')


if __name__ == '__main__':
    main()
