"""Versioned six-dimensional RT table and vectorized effective-cloud inversion.

Units: pressure Pa, ozone DU, AOD550 dimensionless, irradiances W/m².
All direct components are horizontal. No personal exposure interpretation.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy.interpolate import RegularGridInterpolator

AXES = ("sza", "ozone_du", "pressure_pa", "aod550", "albedo", "tau550")
DEFAULT_TABLE = Path(__file__).with_name("data") / "rt.npz"
# Values below 89 degrees are interpolated; the tiny 89–90 tail is faded to zero.
DEFAULT_AXES = {
    "sza": [0, 20, 35, 45, 55, 65, 72, 78, 82, 85, 87, 89],
    "ozone_du": [200, 320, 500],
    "pressure_pa": [50000, 70000, 85000, 105000],
    "aod550": [0, .25, 1],
    "albedo": [0, .5, .85],
    "tau550": [0, .5, 2, 5, 10, 20, 50, 150],
}
FLAG_MEANINGS = {
    1: "shortwave_above_clear_sky",
    2: "shortwave_below_cloud_table_minimum",
    4: "weak_solar_signal",
    8: "nonmonotonic_cloud_response",
    16: "local_column_approximation",
    32: "terrain_screening_approximation",
    64: "low_sun_plane_parallel_approximation",
}


def erythema(wavelength_nm):
    w = np.asarray(wavelength_nm, float)
    return np.where((w < 250) | (w > 400), 0., np.where(w <= 298, 1.,
        np.where(w <= 328, 10. ** (.094 * (298 - w)), 10. ** (.015 * (140 - w)))))


def solar_geometry(times, latitude, longitude):
    """Vectorized NOAA fractional-year approximation, times as UTC datetime64.

    Broadcast time and position arrays explicitly (e.g. time[:,None], lat[None,:]).
    Returns geometric zenith, azimuth clockwise from north, Earth-distance factor.
    """
    t = np.asarray(times, dtype="datetime64[ns]")
    if np.any(np.isnat(t)):
        raise ValueError("Missing UTC time")
    day = (t.astype("datetime64[D]") - t.astype("datetime64[Y]")).astype(float) + 1
    hour = (t - t.astype("datetime64[D]")) / np.timedelta64(1, "h")
    year = t.astype("datetime64[Y]")
    days_in_year = ((year + np.timedelta64(1, "Y")).astype("datetime64[D]")
                    - year.astype("datetime64[D]")).astype(float)
    g = 2 * np.pi / days_in_year * (day - 1 + (hour - 12) / 24)
    eq = 229.18 * (.000075 + .001868*np.cos(g) - .032077*np.sin(g)
                  - .014615*np.cos(2*g) - .040849*np.sin(2*g))
    dec = (.006918 - .399912*np.cos(g) + .070257*np.sin(g)
           - .006758*np.cos(2*g) + .000907*np.sin(2*g)
           - .002697*np.cos(3*g) + .00148*np.sin(3*g))
    ha = np.deg2rad((hour*60 + eq + 4*np.asarray(longitude))/4 - 180)
    lat = np.deg2rad(latitude)
    mu = np.sin(lat)*np.sin(dec) + np.cos(lat)*np.cos(dec)*np.cos(ha)
    z = np.rad2deg(np.arccos(np.clip(mu, -1, 1)))
    az = (np.rad2deg(np.arctan2(np.sin(ha), np.cos(ha)*np.sin(lat)
                               - np.tan(dec)*np.cos(lat))) + 180) % 360
    distance = (1.00011 + .034221*np.cos(g) + .00128*np.sin(g)
                + .000719*np.cos(2*g) + .000077*np.sin(2*g))
    return z, az, distance


def _coordinate(name, x):
    # Log ozone is closer to its power-law UV response; tau uses log(1+tau).
    if name == "ozone_du":
        return np.log(x)
    if name == "tau550":
        return np.log1p(x)
    return x


class RadiationTable:
    def __init__(self, path=DEFAULT_TABLE):
        self.sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        with np.load(path, allow_pickle=False) as data:
            self.axes = {k: data[k].copy() for k in AXES}
            self.values = data["flux"].copy()
            self.metadata = json.loads(str(data["metadata"]))
        if self.metadata.get("schema") == 1:
            raise ValueError("Rejected prototype RT table (schema 1); regenerate with the current builder")
        if self.values.shape != tuple(len(self.axes[k]) for k in AXES) + (4,):
            raise ValueError("Invalid RT table shape")
        if not np.all(np.isfinite(self.values)) or np.any(self.values < 0):
            raise ValueError("Invalid RT table values")
        for a in self.axes.values():
            if a.ndim != 1 or len(a) < 2 or not np.all(np.diff(a) > 0):
                raise ValueError("RT table axes must increase")
        if self.metadata.get("schema", 0) >= 2:
            z = self.axes["sza"][:, None, None, None, None, None]
            albedo = self.axes["albedo"][None, None, None, None, :, None]
            if np.any(self.values[..., :2].sum(axis=-1)*(1-albedo)
                      > 1400*np.cos(np.deg2rad(z))+1e-3):
                raise ValueError("RT table violates solar energy bound")
        # Interpolate totals and direct beams, then recover diffuse by difference.
        # Separate log interpolation of diffuse creates a large negative bias as
        # aerosol scattering transfers energy between direct and diffuse beams.
        channels = np.stack([self.values[..., :2].sum(axis=-1), self.values[..., 0],
                             self.values[..., 2:].sum(axis=-1), self.values[..., 2]], axis=-1)
        self.metadata["runtime_interpolation"] = "log total/direct flux; log ozone; log1p tau; multilinear"
        self._interpolate = RegularGridInterpolator(
            tuple(_coordinate(k, self.axes[k]) for k in AXES),
            np.log(np.maximum(channels, 1e-20)), bounds_error=True)

    def at(self, sza, ozone_du, pressure_pa, aod550, albedo, tau550):
        """Return [..., sw_direct, sw_diffuse, erythemal_direct, erythemal_diffuse].

        No silent clipping of atmospheric inputs or extrapolation. Night output is
        zero; daylight outside the scientific table bounds is rejected.
        """
        arrays = np.broadcast_arrays(sza, ozone_du, pressure_pa, aod550, albedo, tau550)
        if any(not np.all(np.isfinite(a)) for a in arrays):
            raise ValueError("Nonfinite radiation input")
        if np.any((arrays[0] < 0) | (arrays[0] > 180)):
            raise ValueError("Invalid solar zenith")
        for k, a in zip(AXES[1:], arrays[1:]):
            if np.any((a < self.axes[k][0]) | (a > self.axes[k][-1])):
                raise ValueError(f"{k} outside RT table [{self.axes[k][0]}, {self.axes[k][-1]}]")
        z = arrays[0]
        if np.all(z >= 90):
            return np.zeros(z.shape+(4,))
        query = np.column_stack([_coordinate(k, np.minimum(a, 89) if k == "sza" else a).ravel()
                                 for k, a in zip(AXES, arrays)])
        c = np.exp(self._interpolate(query)).reshape(z.shape + (4,))
        result = np.stack([c[..., 1], np.maximum(c[..., 0]-c[..., 1], 0),
                           c[..., 3], np.maximum(c[..., 2]-c[..., 3], 0)], axis=-1)
        result *= np.clip(np.cos(np.deg2rad(z))/np.cos(np.deg2rad(89)), 0, 1)[..., None]
        result[z >= 90] = 0
        return result

    def cloud(self, sza, distance, ozone, pressure, aod, sw_albedo, sw_mean):
        """One effective cloud per interval/cell. sza is [sample,cell].

        Returns tau, scalar extension factor, bit flags. Branch selection is
        explicit; neither this inversion nor excess-clear scaling resolves 3-D
        cloud enhancement or subhourly cloud variability.
        """
        sza = np.asarray(sza)
        sw_mean = np.asarray(sw_mean)
        if sza.ndim != 2 or sw_mean.shape != sza.shape[1:]:
            raise ValueError("Expected solar samples [sample,cell] and mean [cell]")
        if np.any(~np.isfinite(sw_mean)) or np.any(sw_mean < 0):
            raise ValueError("Invalid shortwave mean")
        if np.any(np.all(sza >= 90, axis=0) & (sw_mean > 5)):
            raise ValueError("Substantial shortwave at night: check time/coordinates/radiation semantics")
        tau_axis = self.axes["tau550"]
        curve = np.empty((len(tau_axis), len(sw_mean)))
        for i, tau in enumerate(tau_axis):
            f = self.at(sza, ozone, pressure, aod, sw_albedo, tau)
            curve[i] = (f[..., :2].sum(axis=-1) * distance).mean(axis=0)
        flags = np.zeros(len(sw_mean), dtype=np.uint16)
        flags[np.any((sza > 78) & (sza < 90), axis=0)] |= 64
        flags[np.any(np.diff(curve, axis=0) > 1e-5, axis=0)] |= 8
        weak = curve[0] < 5
        high = (~weak) & (sw_mean > curve[0])
        minimum_index = np.argmin(curve, axis=0)
        minimum = curve[minimum_index, np.arange(len(sw_mean))]
        low = (~weak) & (sw_mean < minimum)
        flags[weak] |= 4
        flags[high] |= 1
        flags[low] |= 2
        result = np.full(len(sw_mean), np.nan)
        scale = np.ones(len(sw_mean))
        result[weak | high] = 0
        result[low] = tau_axis[minimum_index[low]]
        scale[high] = sw_mean[high]/curve[0, high]
        scale[low] = sw_mean[low]/minimum[low]
        # Flux interpolation is log-linear at a single SZA, but the interval
        # average is a sum of exponentials. Bisect the earliest bracketing branch.
        for i in range(len(tau_axis)-1):
            a, b = curve[i:i+2]
            mask = np.isnan(result) & (sw_mean >= np.minimum(a, b)) & (sw_mean <= np.maximum(a, b))
            if not np.any(mask):
                continue
            lo = np.full(mask.sum(), np.log1p(tau_axis[i]))
            hi = np.full(mask.sum(), np.log1p(tau_axis[i+1]))
            # Precompute sample-level component endpoints: no repeated 6-D LUT calls.
            left = self.at(sza[:, mask], np.asarray(ozone)[mask], np.asarray(pressure)[mask],
                           np.asarray(aod)[mask], np.asarray(sw_albedo)[mask], tau_axis[i])[..., :2]
            right = self.at(sza[:, mask], np.asarray(ozone)[mask], np.asarray(pressure)[mask],
                            np.asarray(aod)[mask], np.asarray(sw_albedo)[mask], tau_axis[i+1])[..., :2]
            log_left = np.log(np.maximum(left.sum(axis=-1), 1e-20))
            log_right = np.log(np.maximum(right.sum(axis=-1), 1e-20))
            for _ in range(24):
                mid = (lo+hi)/2
                fraction = (mid-np.log1p(tau_axis[i]))/(np.log1p(tau_axis[i+1])-np.log1p(tau_axis[i]))
                sample = np.exp(log_left + fraction[None, :]*(log_right-log_left))
                value = (sample * np.broadcast_to(distance, sza.shape)[:, mask]).mean(axis=0)
                move_lo = (value > sw_mean[mask]) == (a[mask] > b[mask])
                lo = np.where(move_lo, mid, lo)
                hi = np.where(move_lo, hi, mid)
            result[mask] = np.expm1((lo+hi)/2)
        if np.any(np.isnan(result)):
            raise ValueError("No bracketed effective cloud solution")
        return result, scale, flags
