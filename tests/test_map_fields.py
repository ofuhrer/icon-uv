"""Scientific map rasters preserve category boundaries, missing data and support."""
import base64
import importlib.util
from pathlib import Path
import struct
import zlib

import numpy as np
import pytest

from test_daily import grid

spec = importlib.util.spec_from_file_location('map_fields', Path(__file__).resolve().parents[1]/'examples/map/export_fields.py')
fields = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fields)


def decode_rgba(uri):
    png = base64.b64decode(uri.split(',')[1])
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    offset, data = 8, b''
    while offset < len(png):
        length = struct.unpack('>I', png[offset:offset+4])[0]
        kind, content = png[offset+4:offset+8], png[offset+8:offset+8+length]
        assert zlib.crc32(kind+content) == struct.unpack('>I', png[offset+8+length:offset+12+length])[0]
        if kind == b'IHDR':
            width, height, depth, colour, *_ = struct.unpack('>IIBBBBB', content)
            assert (depth, colour) == (8, 6)
        if kind == b'IDAT':
            data += content
        offset += length+12
    raw = np.frombuffer(zlib.decompress(data), dtype=np.uint8).reshape(height, width*4+1)
    rows = raw[:, 1:].astype(np.uint16)
    for y in range(height):
        if raw[y, 0] == 2 and y:
            rows[y] = (rows[y]+rows[y-1]) % 256
        else:
            assert raw[y, 0] in (0, 2)
    return rows.astype(np.uint8).reshape(height, width, 4)


def decode(uri):
    rgba = decode_rgba(uri)
    return np.where(rgba[..., 3], (rgba[..., 0].astype(int)*256+rgba[..., 1])/100, np.nan)


def test_scalar_png_preserves_zero_missing_and_risk_boundaries():
    values = np.array([[0, np.nan, 2.4999, 2.5, 5.4999, 5.5], [7.4999, 7.5, 10.4999, 10.5, 12.34, 18.999]])
    decoded = decode(fields.png_values(values))
    np.testing.assert_array_equal(np.isnan(decoded), np.isnan(values))
    good = np.isfinite(values)
    assert np.all(abs(decoded[good]-values[good]) < .010001)
    np.testing.assert_array_equal(np.floor(decoded[good]+.5), np.floor(values[good]+.5))
    with pytest.raises(ValueError):
        fields.png_values(np.array([[-1.0]]))


def test_png_filter_roundtrip_preserves_every_numeric_byte():
    values = np.random.default_rng(17).integers(0, 65536, size=(19, 37))/100
    values[0, :3] = [0, np.nan, 655.35]
    values[1::3, 4::5] = np.nan
    rgba = decode_rgba(fields.png_values(values))
    finite = np.isfinite(values)
    expected = np.floor(np.where(finite, values, 0)*100+1e-9).astype(np.uint16)
    np.testing.assert_array_equal(rgba[..., 0].astype(np.uint16)*256+rgba[..., 1], expected)
    np.testing.assert_array_equal(rgba[..., 3], finite*255)
    assert not rgba[..., 2].any()


def test_sparse_native_grid_does_not_fill_distant_map_pixels():
    ds = grid(n=1)
    indices, supported, geometry = fields.raster_support(ds, bbox=(9.7,46.7,9.9,46.9), width=64)
    assert len(indices) == geometry['width']*geometry['height']
    assert supported.any() and (~supported).any()
    assert np.all(indices == 0)
