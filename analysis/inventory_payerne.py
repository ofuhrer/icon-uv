"""Metadata-only inventory: preserve the independent Payerne outcomes unseen."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'work/independent-payerne-20260906'
ENDPOINT = 'https://ws.pangaea.de/es/pangaea/panmd/_search'
NS = {'md': 'http://www.pangaea.de/MetaData'}


def inventory(root=WORK):
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for kind, term in [('uv', 'Ultra-violet'), ('sw', 'Basic and other measurements')]:
        path = root/('inventory_uv_search.json' if kind == 'uv' else 'inventory_sw_combined_search.json')
        if not path.exists():
            query = {'size': 100, 'query': {'bool': {
                'must': {'query_string': {'query': f'Payerne AND "{term}"'}},
                'filter': {'range': {'minDateTime': {'gte': '2024-08-01', 'lt': '2025-10-01'}}}}}}
            result = requests.post(ENDPOINT, json=query, timeout=60)
            result.raise_for_status()
            path.write_text(json.dumps(result.json(), indent=2))
        data = json.loads(path.read_text())
        if data['hits']['total'] > len(data['hits']['hits']):
            raise ValueError('Incomplete inventory response')
        for hit in data['hits']['hits']:
            source = hit['_source']; xml = ET.fromstring(source['xml'])
            title = xml.findtext('md:citation/md:title', namespaces=NS)
            if not title.startswith(term+' measurements' if kind == 'uv' else term):
                raise ValueError(f'Unexpected source: {title}')
            if 'Payerne' not in title:
                raise ValueError('Wrong station')
            fields = []
            for column in xml.findall('.//md:matrixColumn', NS):
                fields.append({k: column.findtext(path, namespaces=NS) for k, path in {
                    'name': 'md:parameter/md:shortName', 'unit': 'md:parameter/md:unit',
                    'instrument': 'md:method/md:name', 'comment': 'md:comment'}.items()})
            rows.append(dict(kind=kind, title=title, doi=source['URI'],
                             start=source['minDateTime'], end=source['maxDateTime'],
                             modified=source['sp-lastModified'], position=source['meanPosition'],
                             fields=fields, xml_sha256=hashlib.sha256(source['xml'].encode()).hexdigest()))
    result = {'status': 'metadata inventoried; source qualification incomplete; outcomes not scored',
              'generated_at': datetime.now(timezone.utc).isoformat(),
              'records': sorted(rows, key=lambda r: (r['kind'], r['start'])),
              'reserved_roster_sha256': hashlib.sha256((ROOT/'work/product-readiness-20260906/payerne_reserved.json').read_bytes()).hexdigest(),
              'snapshots': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(root.glob('inventory_*_search.json'))}}
    (root/'inventory.json').write_text(json.dumps(result, indent=2))
    print({kind: sum(r['kind']==kind for r in rows) for kind in ('uv', 'sw')})


if __name__ == '__main__':
    inventory()
