"""NetCDF compression preserves scientific values, metadata and data types."""
from copy import deepcopy

import netCDF4
import numpy as np
import pytest
import xarray as xr

from icon_uv.data import _netcdf_chunks, write_netcdf


@pytest.mark.parametrize('ensemble', [False, True])
def test_netcdf_compressed_roundtrip(tmp_path, ensemble):
    dims = ('member', 'time', 'cell') if ensemble else ('time', 'cell')
    shape = (3, 7, 31) if ensemble else (7, 31)
    values = np.random.default_rng(42).random(shape).astype('float32')
    values.flat[4] = np.nan
    ds = xr.Dataset({'uvi': (dims, values),
                     'quality_flag': (dims, np.full(shape, 128, dtype='uint16')),
                     'scalar': ((), np.float64(1.25)),
                     'empty': ('empty_dim', np.array([], dtype='float32')),
                     'label': ('poi', ['Geneva', 'Zurich'])},
                    coords={'time': np.datetime64('2026-09-07')+np.arange(7).astype('timedelta64[h]'),
                            'cell': np.arange(31, dtype='int64'),
                            'latitude': ('cell', np.linspace(45.5, 47.5, 31))},
                    attrs={'source': 'compression roundtrip'})
    if ensemble:
        ds = ds.assign_coords(member=np.arange(3, dtype='int64'))
    ds.uvi.attrs['units'] = '1'
    ds.uvi.encoding.update(zlib=True, complevel=2, chunksizes=shape)
    original_encodings = {name: deepcopy(v.encoding) for name, v in ds.variables.items()}
    path = tmp_path/'out.nc'
    write_netcdf(ds, path)
    assert {name: v.encoding for name, v in ds.variables.items()} == original_encodings
    expected = ds.copy()
    expected['scalar'] = expected.scalar.astype('float32')
    with xr.open_dataset(path) as reopened:
        xr.testing.assert_identical(reopened.load(), expected)
    with netCDF4.Dataset(path) as saved:
        for name in ['uvi', 'quality_flag', 'cell', 'latitude']:
            variable = saved[name]
            assert variable.filters()['zlib']
            assert variable.filters()['complevel'] == 4
            assert variable.filters()['shuffle']
            assert np.prod(variable.chunking())*variable.dtype.itemsize <= 4*1024**2
        assert saved['quality_flag'].dtype == np.dtype('uint16')
        assert saved['latitude'].dtype == np.dtype('float64')
        assert saved['time'].units == 'seconds since 1970-01-01'
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('dims,shape', [
    (('member', 'time', 'cell'), (21, 120, 1000000)),
    (('time', 'cell'), (120, 1000000)),
    (('time', 'poi'), (120, 500000)),
    (('x', 'y', 'z'), (10000, 10000, 10000)),
])
def test_netcdf_chunks_bound_large_and_alternative_dimensions(dims, shape):
    variable = xr.Variable(dims, np.broadcast_to(np.array(0., dtype='float32'), shape))
    chunks = _netcdf_chunks(variable, 'float32')
    assert all(1 <= chunk <= size for chunk, size in zip(chunks, shape))
    assert np.prod(chunks)*4 <= 4*1024**2
    if 'member' in dims:
        assert chunks[dims.index('member')] == 21
        assert chunks[dims.index('time')] == 6
