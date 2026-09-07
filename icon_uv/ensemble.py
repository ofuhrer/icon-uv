"""Member identity and reductions; never average atmospheric inputs before UV."""
import json
import math
import warnings

import numpy as np
import xarray as xr


def _expected_members(ds, fallback):
    try:
        expected = json.loads(ds.attrs['ensemble_members']) if 'ensemble_members' in ds.attrs else fallback
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid requested ensemble member IDs') from exc
    if (not isinstance(expected, list) or not expected
            or any(type(m) is not int or not 0 <= m <= 20 for m in expected)
            or len(set(expected)) != len(expected)):
        raise ValueError('Expected nonempty, unique requested ensemble member IDs in 0..20')
    return expected


def member_ids(ds):
    if 'member' not in ds.dims:
        return None
    ids = ds.member.values
    if (ds.member.dims != ('member',) or ids.dtype.kind not in 'iu' or len(ids) < 1
            or len(np.unique(ids)) != len(ids) or np.any((ids < 0) | (ids > 20))):
        raise ValueError('Expected unique ICON-CH2 member IDs in 0..20 (at least one)')
    expected = _expected_members(ds, ids.tolist())
    if not set(ids).issubset(expected):
        raise ValueError('Unexpected ensemble members')
    return ids.tolist()


def map_members(function, ds, *, shared_vars=(), **kwargs):
    """Run the existing physical calculation independently, keeping static axes."""
    ids = member_ids(ds)
    results = []
    for i, m in enumerate(ids, 1):
        if kwargs.get('progress'):
            print(f'UV member {m} ({i}/{len(ids)})', flush=True)
        results.append(function(ds.sel(member=m, drop=True), **kwargs))
    varying = [k for k, v in results[0].data_vars.items() if 'time' in v.dims and k != 'time_bounds' and k not in shared_vars]
    out = xr.concat(results, dim=xr.IndexVariable('member', ids), data_vars=varying,
                    coords='minimal', compat='equals', join='exact')
    out.attrs.pop('member', None)
    out.attrs['ensemble_members'] = ds.attrs.get('ensemble_members', json.dumps(ids))
    out.attrs['ensemble_size'] = len(ids)
    out.attrs['ensemble_method'] = 'independent member UV calculations; common CAMS composition and radiation physics'
    if 'compute_seconds' in out.attrs:
        out.attrs['compute_seconds'] = sum(r.attrs['compute_seconds'] for r in results)
    return out


def required_members(ds):
    expected = _expected_members(ds, member_ids(ds) or [0])
    fraction = float(ds.attrs.get('minimum_member_fraction', .9))
    if not 0 < fraction <= 1:
        raise ValueError('Minimum member fraction must be in (0, 1]')
    return expected, fraction, math.ceil(len(expected)*fraction)


def quantile_available(values, quantile, axis=None):
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='All-NaN slice encountered', category=RuntimeWarning)
        return np.nanquantile(values, quantile, axis=axis)


def ensemble_metadata(ids, quantile=.5, *, expected=None, fraction=.9):
    if not np.isfinite(quantile) or not 0 <= quantile <= 1:
        raise ValueError('Ensemble quantile must be between 0 and 1')
    expected = ids if expected is None else expected
    return dict(member_ids=ids, member_count=len(ids), requested_member_ids=expected,
                minimum_member_fraction=fraction, required_member_count=math.ceil(len(expected)*fraction),
                deterministic_quantile=float(quantile),
                reduction='quantile_of_member_daily_products', quantile_method='linear',
                uncertainty_scope='ICON weather members; common CAMS and UV physics; uncalibrated member frequencies')


def summary(values):
    """Distribution of unrounded member products, including UVI threshold events."""
    values = np.asarray(values, float)
    if np.any(np.isinf(values)) or np.any(values < 0):
        raise ValueError('Ensemble member products must be nonnegative, finite or missing')
    all_values = [float(v) if np.isfinite(v) else None for v in values]
    values = values[np.isfinite(values)]
    if not len(values):
        raise ValueError('No available ensemble member products')
    return dict(member_uvi=all_values, valid_member_count=len(values), p10=float(np.quantile(values, .1)),
                p50=float(np.quantile(values, .5)), p90=float(np.quantile(values, .9)),
                probability_uvi_ge={str(t): float(np.mean(values >= t)) for t in (3, 6, 8, 11)})
