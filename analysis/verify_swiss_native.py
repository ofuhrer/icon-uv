"""Independently decode complete native fields for each archived configuration."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import eccodes as ec


def run(root):
    selected={}
    for path in sorted((root/'icon').glob('????????_00.json')):
        meta=json.loads(path.read_text());selected.setdefault(meta['configuration'],path)
    count=0;checks=[]
    for config,path in selected.items():
        meta=json.loads(path.read_text());raw=np.load(path.with_suffix('.npz'))
        i=list(raw['leads']).index(12)
        refs={tuple(r['parameter']):r for r in meta['records'] if r['endStep']==12}
        source=Path(next(iter(refs.values()))['source']);done=set()
        with source.open('rb') as stream:
            while (g:=ec.codes_grib_new_from_file(stream)) is not None:
                try:
                    key=tuple(ec.codes_get_long(g,k) for k in ('discipline','parameterCategory','parameterNumber'))
                    if key not in refs or ec.codes_get_long(g,'typeOfFirstFixedSurface')!=1:continue
                    ref=refs[key]
                    if hashlib.sha256(ec.codes_get_message(g)).hexdigest()!=ref['sha256']:raise ValueError('Changed source field')
                    # Decode the entire field, unlike extraction via codes_get_elements.
                    values=ec.codes_get_values(g)[raw['cell']]
                    if not np.array_equal(values,raw[ref['field']][i]):raise ValueError('Native element mismatch')
                    count+=len(values);done.add(key)
                finally:ec.codes_release(g)
                if done==set(refs):break
        if done!=set(refs):raise ValueError('Missing native reference field')
        checks.append(dict(configuration=config,case=path.stem,lead=12,fields=len(done)))
    (root/'native_full_decode_verification.json').write_text(json.dumps(dict(status='passed',values=count,checks=checks),indent=2))
    print('Verified',count,'native values by independent full-field decoding',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root)
