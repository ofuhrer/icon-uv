"""Shared sampled UV reconstruction from validated hourly atmospheric state."""
import numpy as np
from .radiation import solar_geometry


from .state import finite_state


def evaluate_uv(state, times, table, *, clear_sky=False, horizon_degrees=None):
    """Return horizontal components, screened UVI, availability and quality flags.

    state is one hour on one or more cells. Missing inputs remain NaN. Horizon
    screening is supported for a single explicitly adjusted point.
    """
    z, az, distance = solar_geometry(times[:, None], state.latitude.values[None, :], state.longitude.values[None, :])
    keys = ('ozone_du', 'pressure_pa', 'aod550', 'uv_albedo', 'effective_cloud_tau550', 'cloud_scale')
    valid = finite_state(state)
    components = np.full(z.shape+(2,), np.nan)
    if valid.any():
        args = [state[k].values[valid] for k in keys[:5]]
        if clear_sky:
            args[-1] = 0
        flux = table.at(z[:, valid], *args)[..., 2:]
        scale = 1 if clear_sky else state.cloud_scale.values[valid]
        components[:, valid] = flux*np.broadcast_to(distance, z.shape)[:, valid, None]*np.asarray(scale)[..., None]
    flags = state.quality_flag.values.astype(np.uint16).copy()
    flags[~valid] |= 128
    flags[np.any((z > 78) & (z < 90), axis=0)] |= 64
    screened = 40*components.sum(axis=-1)
    if horizon_degrees is not None:
        if state.sizes['cell'] != 1:
            raise ValueError('A terrain horizon applies to one point')
        horizon = np.asarray(horizon_degrees)
        h = np.interp(az, np.linspace(0, 360, len(horizon)+1), np.r_[horizon, horizon[0]])
        sky = np.mean(np.cos(np.deg2rad(horizon))**2)
        screened = 40*(components[..., 0]*(90-z > h) + components[..., 1]*sky)
        flags |= 32
    return components, screened, valid, flags
