"""Frozen, unfitted physical stress experiment for daily-product decisions."""
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
import pandas as pd

from icon_uv.build_table import ReferenceSolver
from icon_uv.daily import display_value
from icon_uv.radiation import RadiationTable, erythema

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/product-physics-20260906'
LIB = ROOT / 'work/legacy-icon-nwp/.uv-work/libRadtran-2.0.6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def direct(config, lib=LIB, root=WORK):
    """Independent input deck with explicit profile; retain every solver output."""
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    output = root / 'calculations' / key
    output.mkdir(parents=True, exist_ok=True)
    z, height, albedo, tau = (config[k] for k in ('sza', 'height_m', 'albedo', 'tau'))
    pressure = 101325*np.exp(-height/8434)
    with tempfile.TemporaryDirectory(prefix='product-physics-') as tmp:
        tmp = Path(tmp)
        np.savetxt(tmp/'wavelength.dat', np.r_[np.arange(250, 400.25, .5), 550])
        (tmp/'cloud.dat').write_text(f'{height/1000+2} 0 10\n{height/1000+1} .1 10\n')
        base = (f'data_files_path {lib}/data\natmosphere_file {lib}/data/atmmod/{config["profile"]}.dat\n'
                f'altitude {height/1000}\npressure {pressure/100}\nmol_modify O3 300 DU\n'
                f'mol_modify H2O {config["water_mm"]} MM\nsza {z}\nalbedo {albedo}\n'
                'rte_solver disort\nnumber_of_streams 8\nquiet\naerosol_default\n'
                f'aerosol_angstrom 1.3 {.1*.55**1.3}\naerosol_modify ssa set 0.95\n'
                'aerosol_modify gg set 0.7\n')
        if tau:
            base += f'wc_file 1D cloud.dat\nwc_properties hu\nwc_modify tau550 set {tau}\n'
        decks = {'uv': base + f'source solar {lib}/data/solar_flux/atlas_plus_modtran\n'
                 'mol_abs_param crs\nwavelength 250 550\nwavelength_grid_file wavelength.dat\n'
                 'output_user lambda edir edn\n',
                 'sw': base + 'source solar\nmol_abs_param kato2\noutput_process sum\noutput_user edir edn\n'}
        results = {}
        for name, deck in decks.items():
            (output/f'{name}.inp').write_text(deck)
            result = subprocess.run([str(lib/'bin/uvspec')], input=deck, text=True,
                                    capture_output=True, timeout=120, cwd=tmp, check=True)
            (output/f'{name}.out').write_text(result.stdout)
            (output/f'{name}.stderr').write_text(result.stderr)
            results[name] = np.loadtxt(io.StringIO(result.stdout))
        for name in ('wavelength.dat', 'cloud.dat'):
            (output/name).write_bytes((tmp/name).read_bytes())
    uv = results['uv']; uv = uv[uv[:, 0] <= 400]
    weighted = np.trapezoid(uv[:, 1:]*erythema(uv[:, 0])[:, None]/1000, uv[:, 0], axis=0)
    flux = np.r_[results['sw'], weighted]
    if not np.isfinite(flux).all() or np.any(flux < -1e-10):
        raise ValueError('Invalid direct flux')
    if flux[:2].sum()*(1-albedo) > 1400*np.cos(np.deg2rad(z))+1e-3:
        raise ValueError('Direct calculation violates solar energy bound')
    (output/'config.json').write_text(json.dumps(config, indent=2))
    return np.maximum(flux, 0)


def run(root=WORK):
    root.mkdir(parents=True, exist_ok=True)
    table = RadiationTable()
    reference = ReferenceSolver(LIB, root/'reference-cache')
    identity = {'protocol_sha256': sha(ROOT/'analysis/PRODUCT_PHYSICS_PLAN.md'),
                'code_sha256': sha(__file__), 'table_sha256': table.sha256,
                'solver': reference.provenance}
    frozen = root/'frozen_identity.json'
    if frozen.exists() and json.loads(frozen.read_text()) != identity:
        raise ValueError('Changed frozen physics inputs; use a new experiment directory')
    frozen.write_text(json.dumps(identity, indent=2))
    configs = [dict(sza=z, height_m=h, albedo=a, tau=t, profile=p, water_mm=w)
               for z, h, a, t in product((25, 65), (500, 1500, 3000), (.05, .8), (0, 10))
               for p, w in [('afglms', 20), ('afglmw', 20), ('afglmw', 5)]]
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        fluxes = list(pool.map(lambda c: direct(c, root=root), configs))
    point = (25, 300, 101325*np.exp(-500/8434), .1, .05, 0)
    bridge = float(np.max(np.abs(fluxes[0]-reference(point))))
    if bridge > 1e-8:
        raise ValueError(f'Independent input-deck bridge failed: {bridge}')
    rows = []
    for config, flux in zip(configs, fluxes):
        z, h, a = (config[k] for k in ('sza', 'height_m', 'albedo'))
        pressure = 101325*np.exp(-h/8434)
        tau, scale, flags = table.cloud(np.array([[z]]), np.ones((1, 1)), np.array([300]),
                                       np.array([pressure]), np.array([.1]), np.array([a]),
                                       np.array([flux[:2].sum()]))
        predicted = float(table.at(z, 300, pressure, .1, a, tau[0])[2:].sum()*scale[0]*40)
        observed = float(flux[2:].sum()*40)
        pi, pc = display_value(predicted); oi, oc = display_value(observed)
        rows.append(dict(config, reference_uvi=observed, inferred_uvi=predicted,
                         error=predicted-observed, reference_sw=float(flux[:2].sum()),
                         inferred_tau=float(tau[0]), scale=float(scale[0]), flag=int(flags[0]),
                         display_error=pi-oi, same_category=pc==oc))
    frame = pd.DataFrame(rows); frame.to_csv(root/'pairs.csv', index=False)
    report = {'states': len(configs), 'bridge_max_flux_difference': bridge,
              'runtime_seconds': time.monotonic()-start, 'profiles': {}}
    for (profile, water), group in frame.groupby(['profile', 'water_mm']):
        report['profiles'][f'{profile}_{water}mm'] = dict(n=len(group), mae=float(group.error.abs().mean()),
            max_absolute_error=float(group.error.abs().max()),
            within_one=float((group.display_error.abs() <= 1).mean()),
            same_category=float(group.same_category.mean()))
    report['artifacts'] = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
                           if p.is_file() and p.name not in ('summary.json',)}
    (root/'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'artifacts'}, indent=2), flush=True)


if __name__ == '__main__':
    run()
