"""Verify the complete local-input → native UV → daily JSON delivery path."""
from importlib.metadata import version
from pathlib import Path
import hashlib
import json
import time

from jsonschema import Draft202012Validator, FormatChecker
import numpy as np
import xarray as xr

from icon_uv.daily import export_daily, select_support, write_json_atomic
from icon_uv.data import load_cams, write_netcdf
from icon_uv.products import compute_grid

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replay():
    start = time.monotonic()
    source = ROOT/'work/product-readiness-20260906'
    output = ROOT/'work/product-delivery-20260906'; output.mkdir(exist_ok=True)
    identity = json.loads((source/'example_identity.json').read_text())
    for name, expected in identity['inputs'].items():
        if sha(source/name) != expected:
            raise ValueError(f'Changed frozen example input: {name}')
    catalog_path = ROOT/'analysis/product_locations.example.json'
    if sha(catalog_path) != identity['catalog_sha256']:
        raise ValueError('Changed example catalog')
    catalog = json.loads(catalog_path.read_text())
    with xr.open_dataset(source/'icon_20260906_00.nc') as full:
        selected = np.unique(np.concatenate([select_support(full, e) for e in catalog['entries']]))
        icon = full.isel(cell=selected).load()
    cams = load_cams(source/'cams_20260905_12.grib')
    grid = compute_grid(icon, cams, samples=12)
    path = output/'uv_product_support.nc'; write_netcdf(grid, path)
    differences = {}
    with xr.open_dataset(source/'uv_product_support_20260906.nc') as expected, xr.open_dataset(path) as persisted:
        np.testing.assert_array_equal(persisted.cell, expected.cell)
        np.testing.assert_array_equal(persisted.time, expected.time)
        for field in ('uvi', 'ozone_du', 'aod550', 'uv_albedo', 'effective_cloud_tau550', 'cloud_scale', 'quality_flag'):
            differences[field] = float(np.max(abs(persisted[field].values-expected[field].values)))
            np.testing.assert_array_equal(persisted[field], expected[field])
    with xr.open_dataset(path) as saved:
        payload = export_daily(saved, catalog, '2026-09-06T06:00:00Z', input_sha256=sha(path))
    schema = json.loads((ROOT/'icon_uv/data/daily-uv-v1.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    expected_payload = json.loads((source/'product-example.json').read_text())
    # NetCDF embeds the measured compute runtime; its file hash legitimately differs.
    expected_payload['input_sha256'] = payload['input_sha256']
    if payload != expected_payload:
        raise ValueError('Daily payload differs from frozen example beyond source-file identity')
    write_json_atomic(payload, output/'product.json')
    result = dict(status='passed', entries=len(payload['entries']), native_cells=len(selected),
                  processing_seconds=time.monotonic()-start, network_acquisition_included=False,
                  maximum_absolute_grid_differences=differences, schema_valid=True,
                  frozen_payload_equal_except_new_grid_sha256=True,
                  packages={p:version(p) for p in ('numpy','scipy','xarray','netCDF4','eccodes','jsonschema')},
                  inputs=identity,
                  source_hashes={str(p.relative_to(ROOT)):sha(p) for p in
                                 [Path(__file__),ROOT/'icon_uv/daily.py',ROOT/'icon_uv/products.py',
                                  ROOT/'icon_uv/data.py',ROOT/'icon_uv/radiation.py',
                                  ROOT/'icon_uv/data/daily-uv-v1.schema.json']},
                  outputs={p.name:sha(p) for p in [path,output/'product.json']})
    write_json_atomic(result, output/'verification.json')
    print(json.dumps({k:result[k] for k in ('status','entries','native_cells','processing_seconds')},indent=2))


if __name__ == '__main__':
    replay()
