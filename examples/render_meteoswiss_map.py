"""Build a static UV map page with separate, refreshable JSON data files."""

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


def validate_products(payload, fields=None):
    """Reject mixed source products before publishing a map bundle."""
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


def render(data_urls):
    """Return static HTML containing data URLs, never forecast values."""
    here = Path(__file__).parent
    template = (here / 'meteoswiss_map.template.html').read_text(encoding='utf-8')
    replacements = {
        '__LEAFLET_CSS__': (here / 'vendor/leaflet-1.9.4.css').read_text(),
        '__LEAFLET_JS__': (here / 'vendor/leaflet-1.9.4.js').read_text().split('//# sourceMappingURL=')[0],
        '__LEAFLET_LICENSE__': (here / 'vendor/leaflet-LICENSE').read_text(),
        '__DATA_URLS__': script_json(data_urls),
    }
    # One pass prevents replacement tokens in catalog text from becoming markup.
    import re
    return re.sub('|'.join(map(re.escape, replacements)), lambda m: replacements[m[0]], template)


def write_bundle(input_path, fields_path, output, cache):
    """Place the page and its data side by side for any static HTTP server."""
    from urllib.parse import quote

    if output.resolve() in {p.resolve() for p in (input_path, fields_path) if p is not None}:
        raise ValueError('Input JSON and output HTML must differ')
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    fields = json.loads(fields_path.read_text(encoding='utf-8')) if fields_path else None
    validate_products(payload, fields)
    tiles = basemap(cache)
    output.parent.mkdir(parents=True, exist_ok=True)
    urls = {}
    for kind, data in [('locations', payload), ('fields', fields), ('basemap', tiles)]:
        if data is None:
            urls[kind] = None
            continue
        target = output.with_name(output.stem+'.'+kind+'.json')
        urls[kind] = quote(target.name)
        content = json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+'\n'
        if not target.exists() or target.read_text(encoding='utf-8') != content:
            target.write_text(content, encoding='utf-8')
    document = render(urls)
    if not output.exists() or output.read_text(encoding='utf-8') != document:
        output.write_text(document, encoding='utf-8')
    return urls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).with_name('meteoswiss_map.locations.json'),
                        help='Daily UV JSON (default: bundled example snapshot)')
    parser.add_argument('--output', type=Path, default=Path('work/meteoswiss-map.html'))
    parser.add_argument('--fields', type=Path, help='Daily field JSON from meteoswiss_fields.py')
    parser.add_argument('--cache', type=Path, default=Path('work/swisstopo-relief-tiles'))
    args = parser.parse_args()
    field_path = args.fields
    if field_path is None and args.input.resolve() == Path(__file__).with_name('meteoswiss_map.locations.json').resolve():
        field_path = Path(__file__).with_name('meteoswiss_map.fields.json')
    urls = write_bundle(args.input, field_path, args.output, args.cache)
    print(f'{args.output} ({args.output.stat().st_size / 1024:.0f} KiB HTML)')
    print('Data: '+', '.join(url for url in urls.values() if url))
    print('Serve the output directory over HTTP to view the page.')


if __name__ == '__main__':
    main()
