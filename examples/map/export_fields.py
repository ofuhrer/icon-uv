"""Export four days of native-terrain UV fields as compact map rasters."""

import argparse
import base64
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import struct
import zlib
from zoneinfo import ZoneInfo

import numpy as np
from scipy.spatial import cKDTree
import xarray as xr

from icon_uv.daily import PEAK_DEFINITION, daily_cells, utc_instant, write_json_atomic

RADIUS = 6371000.0


def mercator(latitude, longitude):
    return np.column_stack((RADIUS*np.deg2rad(longitude),
                            RADIUS*np.arcsinh(np.tan(np.deg2rad(latitude)))))


def raster_support(grid, bbox=(5.9, 45.75, 10.6, 47.85), width=360):
    """Nearest native cell within 3 km; preserve holes in sparse source grids."""
    w, s, e, n = bbox
    if not (32 <= width <= 2048 and -180 <= w < e <= 180 and -85 < s < n < 85):
        raise ValueError('Invalid raster bounds or width (32..2048)')
    (x0, y0), (x1, y1) = mercator([s, n], [w, e])
    height = max(1, round(width*(y1-y0)/(x1-x0)))
    x = x0+(np.arange(width)+.5)*(x1-x0)/width
    y = y1-(np.arange(height)+.5)*(y1-y0)/height
    xx, yy = np.meshgrid(x, y)
    tree = cKDTree(mercator(grid.latitude.values, grid.longitude.values))
    distance, indices = tree.query(np.column_stack((xx.ravel(), yy.ravel())))
    latitude = np.arctan(np.sinh(yy.ravel()/RADIUS))
    inside = distance*np.cos(latitude) <= 3000
    return indices, inside, dict(width=width, height=height, bounds=[[s,w],[n,e]])


def png_values(values):
    """RGBA PNG: red/green hold unsigned UVI*100; alpha zero means unavailable.

    UVI is truncated to 0.01 to preserve integer/category boundaries.
    No palette, gamma correction or lossy image conversion. Browser code decodes
    these numerical bytes before applying the common UV category colours.
    """
    values = np.asarray(values)
    finite = np.isfinite(values)
    if np.any(values[finite] < 0) or np.any(values[finite] > 655.35):
        raise ValueError('UVI outside lossless raster encoding range')
    encoded = np.floor(np.where(finite, values, 0)*100+1e-9).astype(np.uint16)
    rgba = np.zeros(values.shape+(4,), dtype=np.uint8)
    rgba[..., 0] = encoded >> 8
    rgba[..., 1] = encoded & 255
    rgba[..., 3] = np.where(finite, 255, 0)
    height, width = values.shape
    raw = b''.join(b'\0'+row.tobytes() for row in rgba)

    def chunk(kind, content):
        return struct.pack('>I', len(content))+kind+content+struct.pack('>I', zlib.crc32(kind+content))

    png = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
           +chunk(b'IDAT', zlib.compress(raw, 9))+chunk(b'IEND', b''))
    return 'data:image/png;base64,'+base64.b64encode(png).decode()


def export_fields(grid, issued_at, input_sha256, *, width=360):
    """Daily 30-minute peaks on model terrain, with and without cloud effects."""
    issue = utc_instant(issued_at)
    for key, limit in [('forecast_reference_time', 24), ('cams_reference_time', 48)]:
        age = (issue-utc_instant(grid.attrs[key])).total_seconds()/3600
        if not 0 <= age <= limit:
            raise ValueError('Field export requires source cycles fresh at issuance')
    first = issue.astimezone(ZoneInfo('Europe/Zurich')).date()
    indices, inside, geometry = raster_support(grid, width=width)
    # Only calculate cells that contribute to a raster pixel.
    cells, inverse = np.unique(indices, return_inverse=True)
    local = grid.isel(cell=cells)
    days = []
    for d in range(4):
        date = str(first+timedelta(days=d))
        day = {'valid_date': date}
        for mode in ('forecast', 'clear_sky'):
            result = daily_cells(local, date, clear_sky=mode == 'clear_sky')
            values = np.where(inside, result['uvi'][inverse], np.nan)
            day[mode] = png_values(values.reshape(geometry['height'], geometry['width']))
        days.append(day)
        print(f'UV map fields: {date}', flush=True)
    return dict(schema_version='uv-map-fields-v1', issued_at=issue.isoformat(),
                input_sha256=input_sha256, radiation_table_sha256=grid.attrs['radiation_table_sha256'],
                icon_reference_time=grid.attrs['forecast_reference_time'],
                cams_reference_time=grid.attrs['cams_reference_time'],
                peak_definition=PEAK_DEFINITION, projection='EPSG:3857',
                encoding='png-rg-uvi-times-100-alpha-valid',
                spatial_method='nearest native cell within 3 km; no gap filling',
                surface='native model terrain, horizontal open horizon',
                source_cells=int(grid.sizes['cell']), **geometry, days=days)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grid', type=Path, required=True)
    parser.add_argument('--issued-at', required=True)
    parser.add_argument('--output', type=Path, default=Path('work/meteoswiss-map.fields.json'))
    parser.add_argument('--width', type=int, default=360, help='Raster columns; native model resolution is unchanged')
    args = parser.parse_args()
    if args.grid.resolve() == args.output.resolve():
        parser.error('Input grid and output JSON must differ')
    with args.grid.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    with xr.open_dataset(args.grid) as grid:
        fields = export_fields(grid.load(), args.issued_at, digest, width=args.width)
    write_json_atomic(fields, args.output)
    print(args.output)


if __name__ == '__main__':
    main()
