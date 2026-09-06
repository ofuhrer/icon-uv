"""Read the documented DWH catalog using the installed client's normal auth.

Run on Balfrin with the same JRETRIEVE_CONF_* environment as the wrapper.
Configuration and authentication headers are never printed or saved.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the service credential to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(path, output):
    if not (path.startswith('/jretrieve/api/v1/pointdatacatalog/') or
            path == '/documentation/jretrieve/latest/java/'):
        raise ValueError('Only catalog or documented client documentation allowed')
    client = runpy.run_path('/oprusers/osm/opr.inn/bin/jretrievedwh.py', run_name='catalog_client')
    cfg = client['exec_conf_file']()
    origin = urllib.parse.urlsplit(cfg.get('jretrieve_url', 'https://service.meteoswiss.ch'))
    if origin.scheme != 'https' or origin.hostname not in (
        'service.meteoswiss.ch','servicedevt.meteoswiss.ch','servicedepl.meteoswiss.ch'):
        raise ValueError('Unexpected configured DWH origin')
    request = urllib.request.Request('https://'+origin.netloc+path)
    request.add_header('Authorization', cfg['auth_header'])
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        record = {'path':path,'status':error.code}
        if error.code == 400:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(error.read())
        output.with_suffix('.status.json').write_text(json.dumps(record, indent=2))
        print(json.dumps(record))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)
    print(json.dumps({'path':path,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('path'); parser.add_argument('output',type=Path)
    args=parser.parse_args(); fetch(args.path,args.output)
