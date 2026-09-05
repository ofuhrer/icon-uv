"""Optional developer tool: generate the runtime table with libRadtran 2.0.6.

The external executable is needed only here, not when installing/running icon-uv.
The scientifically meaningful configuration is embedded in every table/cache key.
"""
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from pathlib import Path
import hashlib
import io
import json
import subprocess
import tempfile
import time

import numpy as np

from .radiation import AXES, DEFAULT_AXES, erythema

CONFIG = {"schema": 2, "libRadtran": "2.0.6", "streams": 8, "spacing_nm": .5,
          "geometry": "plane-parallel DISORT; low-sun approximation flagged above 78 degrees",
          "atmosphere": "afglms", "water_mm": 20, "angstrom": 1.3,
          "aerosol_ssa": .95, "aerosol_g": .7,
          "cloud": "liquid, 1–2 km above pressure-equivalent surface, reff=10 um",
          "pressure_height": "max(0,-8434*log(p/101325)) m",
          "irradiance": "1 AU; horizontal; sw direct,diffuse; erythemal direct,diffuse W m-2"}


def reference(lib, point, cache, *, spacing=.5, streams=8, water=20):
    lib, cache = Path(lib).resolve(), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    config = dict(CONFIG, spacing_nm=spacing, streams=streams, water_mm=water)
    key = hashlib.sha256(json.dumps([config, list(map(float, point))], sort_keys=True).encode()).hexdigest()
    path = cache / (key + ".npz")
    if path.exists():
        with np.load(path) as f:
            return f["flux"]
    z, ozone, pressure, aod, albedo, tau = point
    height = max(0, -8.434 * np.log(pressure/101325))
    with tempfile.TemporaryDirectory(prefix="icon-uv-rt-") as tmp:
        tmp = Path(tmp)
        np.savetxt(tmp/"wavelength.dat", np.r_[np.arange(250, 400+spacing/2, spacing), 550])
        (tmp/"cloud.dat").write_text(f"{height+2} 0 10\n{height+1} .1 10\n")
        base = (f"data_files_path {lib}/data\natmosphere_file {lib}/data/atmmod/afglms.dat\n"
                f"altitude {height}\npressure {pressure/100}\nmol_modify O3 {ozone} DU\n"
                f"mol_modify H2O {water} MM\nsza {z}\nalbedo {albedo}\n"
                f"rte_solver disort\nnumber_of_streams {streams}\nquiet\n"
                f"aerosol_default\naerosol_angstrom 1.3 {aod*.55**1.3}\n"
                "aerosol_modify ssa set 0.95\naerosol_modify gg set 0.7\n")
        if tau > 0:
            base += f"wc_file 1D {tmp}/cloud.dat\nwc_properties hu\nwc_modify tau550 set {tau}\n"
        uv = base + (f"source solar {lib}/data/solar_flux/atlas_plus_modtran\n"
                     f"mol_abs_param crs\nwavelength 250 550\nwavelength_grid_file {tmp}/wavelength.dat\n"
                     "output_user lambda edir edn\n")
        sw = base + "source solar\nmol_abs_param kato2\noutput_process sum\noutput_user edir edn\n"
        values = []
        for inp in (uv, sw):
            p = subprocess.run([str(lib/"bin/uvspec")], input=inp, text=True,
                               capture_output=True, timeout=120, cwd=tmp)
            if p.returncode:
                raise RuntimeError(p.stderr[-2000:])
            values.append(np.loadtxt(io.StringIO(p.stdout)))
        spectrum, broadband = values
        spectrum = spectrum[spectrum[:, 0] <= 400]
        weighted = np.trapezoid(spectrum[:, 1:]*erythema(spectrum[:, 0])[:, None]/1000,
                                spectrum[:, 0], axis=0)
        flux = np.r_[broadband, weighted]
        if np.any(~np.isfinite(flux)) or np.any(flux < -1e-10):
            raise ValueError("Invalid RT reference result")
        flux = np.maximum(flux, 0)
        # Independent energy bound, not agreement with the same solver. This
        # catches the large thick-cloud/low-sun failures found with the initial
        # pseudo-spherical configuration. 1400 W/m2 is a conservative 1-AU bound.
        if flux[:2].sum()*(1-albedo) > 1400*np.cos(np.deg2rad(z))+1e-3:
            raise ValueError("RT reference violates plane-parallel solar energy bound")
        np.savez_compressed(path, flux=flux)
        return flux


def build(lib, output, cache, axes=None, workers=4):
    axes = DEFAULT_AXES if axes is None else axes
    shape = tuple(len(axes[k]) for k in AXES)
    indices = list(product(*(range(n) for n in shape)))
    flux = np.empty(shape+(4,))
    start = time.monotonic()

    def task(index):
        point = [axes[k][i] for k, i in zip(AXES, index)]
        return index, reference(lib, point, cache)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (index, f) in enumerate(pool.map(task, indices), 1):
            flux[index] = f
            if n % 100 == 0 or n == len(indices):
                print(f"RT columns {n}/{len(indices)}; {time.monotonic()-start:.1f}s", flush=True)
    meta = dict(CONFIG, columns=len(indices), seconds=time.monotonic()-start,
                interpolation="log flux, log ozone, log1p tau; multilinear other axes")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **axes, flux=flux, metadata=json.dumps(meta, sort_keys=True))
