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
import os
import subprocess
import tempfile
from threading import Lock
import time

import numpy as np

from .radiation import AXES, DEFAULT_AXES, erythema
from . import radiation

CONFIG = {"schema": 2, "libRadtran": "2.0.6", "streams": 8, "spacing_nm": .5,
          "geometry": "plane-parallel DISORT; low-sun approximation flagged above 78 degrees",
          "atmosphere": "afglms", "water_mm": 20, "angstrom": 1.3,
          "aerosol_ssa": .95, "aerosol_g": .7,
          "cloud": "liquid, 1–2 km above pressure-equivalent surface, reff=10 um",
          "pressure_height": "max(0,-8434*log(p/101325)) m",
          "irradiance": "1 AU; horizontal; sw direct,diffuse; erythemal direct,diffuse W m-2"}


def _file_sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


class ReferenceSolver:
    """Identify a solver once per batch; keep its installation immutable while running.

    Content identities survive relocation. Legacy unqualified cache files remain
    untouched, but are not read. Runtime grid/POI calculations do not use this class.
    """
    def __init__(self, lib, cache):
        self.lib = Path(lib).resolve()
        binary = self.lib / "bin/uvspec"
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError("libRadtran requires an existing executable bin/uvspec")
        data = self.lib / "data"
        files = sorted(p for p in data.rglob("*") if p.is_file())
        if not files:
            raise ValueError("libRadtran requires a nonempty data directory")
        manifest = [(p.relative_to(data).as_posix(), _file_sha256(p)) for p in files]
        implementation = [_file_sha256(__file__), _file_sha256(radiation.__file__)]
        self.provenance = {
            "cache_schema": 1, "solver_sha256": _file_sha256(binary),
            "data_sha256": hashlib.sha256(json.dumps(manifest).encode()).hexdigest(),
            "data_files": len(files),
            "implementation_sha256": hashlib.sha256(json.dumps(implementation).encode()).hexdigest(),
        }
        identity = json.dumps(self.provenance, sort_keys=True)
        self.directory = Path(cache) / hashlib.sha256(identity.encode()).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "manifest.json").write_text(identity + "\n")
        self._lock = Lock()
        self._hits = self._computed = 0

    def cache_info(self):
        with self._lock:
            return {"hits": self._hits, "computed": self._computed}

    def __call__(self, point, *, spacing=.5, streams=8, water=20):
        config = dict(CONFIG, spacing_nm=spacing, streams=streams, water_mm=water)
        key = hashlib.sha256(json.dumps([config, list(map(float, point))], sort_keys=True).encode()).hexdigest()
        path = self.directory / (key + ".npz")
        if path.exists():
            with np.load(path, allow_pickle=False) as f:
                flux = f["flux"]
            with self._lock:
                self._hits += 1
            return flux
        flux = _calculate_reference(self.lib, point, spacing=spacing, streams=streams, water=water)
        # Readers must not observe a partially written result from another worker.
        with tempfile.NamedTemporaryFile(dir=self.directory, suffix=".npz", delete=False) as f:
            tmp = Path(f.name)
        try:
            with tmp.open("wb") as f:
                np.savez_compressed(f, flux=flux)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
        with self._lock:
            self._computed += 1
        return flux


def reference(lib, point, cache, *, spacing=.5, streams=8, water=20):
    """One-off reference; use ReferenceSolver to hash the installation once per batch."""
    return ReferenceSolver(lib, cache)(point, spacing=spacing, streams=streams, water=water)


def _calculate_reference(lib, point, *, spacing=.5, streams=8, water=20):
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
        return flux


def build(lib, output, cache, axes=None, workers=4):
    solver = ReferenceSolver(lib, cache)
    axes = DEFAULT_AXES if axes is None else axes
    shape = tuple(len(axes[k]) for k in AXES)
    indices = list(product(*(range(n) for n in shape)))
    flux = np.empty(shape+(4,))
    start = time.monotonic()

    def task(index):
        point = [axes[k][i] for k, i in zip(AXES, index)]
        return index, solver(point)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (index, f) in enumerate(pool.map(task, indices), 1):
            flux[index] = f
            if n % 100 == 0 or n == len(indices):
                print(f"RT columns {n}/{len(indices)}; {time.monotonic()-start:.1f}s", flush=True)
    meta = dict(CONFIG, columns=len(indices), seconds=time.monotonic()-start,
                interpolation="log flux, log ozone, log1p tau; multilinear other axes",
                reference_provenance=solver.provenance, reference_cache=solver.cache_info())
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **axes, flux=flux, metadata=json.dumps(meta, sort_keys=True))
