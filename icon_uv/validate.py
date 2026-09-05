"""Deterministic numerical qualification against withheld libRadtran columns.

This is not observation validation. No random tuning split or hidden calibration.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import json

import numpy as np

from .build_table import reference
from .radiation import RadiationTable


def validate(table, lib, cache, output, count=80, seed=20260905):
    rng = np.random.default_rng(seed)
    # Sample broad physical regimes; all coordinates withheld from table nodes.
    points = np.column_stack([rng.uniform(max(25, table.axes["sza"][0]), min(85, table.axes["sza"][-1]), count), rng.uniform(230, 450, count),
                              rng.uniform(56000, 101000, count), rng.uniform(.01, .65, count),
                              rng.uniform(.02, .8, count), np.expm1(rng.uniform(0, np.log(101), count))])
    points[:count//4, -1] = 0  # include clear sky, not only cloudy cases
    with ThreadPoolExecutor(max_workers=4) as pool:
        truth = np.array(list(pool.map(lambda p: reference(lib, p, cache), points)))
    prediction = table.at(*points.T)
    uvi = 40*truth[:, 2:].sum(axis=-1)
    estimated = 40*prediction[:, 2:].sum(axis=-1)
    mask = uvi >= 1
    relative = (estimated[mask]-uvi[mask])/uvi[mask]
    # Single-time SW inversion, not the same as direct forward interpolation.
    sw = truth[:, :2].sum(axis=-1)
    tau, scale, flags = table.cloud(points[:, 0][None, :], 1., points[:, 1], points[:, 2],
                                    points[:, 3], points[:, 4], sw)
    reconstructed = 40*table.at(*points[:, :5].T, tau)[:, 2:].sum(axis=-1)*scale
    inverse_relative = (reconstructed[mask]-uvi[mask])/uvi[mask]
    # The real pipeline uses different broadband and UV albedos. Test that path
    # explicitly: same cloud/column, a distinct broadband reference calculation.
    sw_points = points.copy()
    sw_points[:, 4] = .12 + .65*points[:, 4]
    with ThreadPoolExecutor(max_workers=4) as pool:
        sw_truth = np.array(list(pool.map(lambda p: reference(lib, p, cache), sw_points)))[:, :2].sum(axis=-1)
    paired_tau, paired_scale, _ = table.cloud(points[:, 0][None, :], 1., points[:, 1], points[:, 2],
                                               points[:, 3], sw_points[:, 4], sw_truth)
    paired_uvi = 40*table.at(*points[:, :5].T, paired_tau)[:, 2:].sum(axis=-1)*paired_scale
    paired_relative = (paired_uvi[mask]-uvi[mask])/uvi[mask]
    resolution_points = np.array([[35., 300., 95000., .15, .05, 0.],
                                  [60., 280., 65000., .1, .8, 10.],
                                  [80., 350., 85000., .3, .2, 30.]])
    resolution = []
    for point in resolution_points:
        standard = 40*reference(lib, point, cache)[2:].sum()
        fine = 40*reference(lib, point, cache, spacing=.25)[2:].sum()
        streams = 40*reference(lib, point, cache, streams=16)[2:].sum()
        resolution.append({"point": point.tolist(), "standard_uvi": float(standard),
                           "quarter_nm_relative_change": float(fine/standard-1),
                           "sixteen_stream_relative_change": float(streams/standard-1)})
    water_cases = []
    for water in (10, 40):
        point = np.array([50., 300., 95000., .15, .15, 5.])
        actual = reference(lib, point, cache, water=water)
        t, sc, _ = table.cloud(point[:1, None], 1., point[1:2], point[2:3], point[3:4],
                               point[4:5], np.array([actual[:2].sum()]))
        estimate = 40*table.at(*point[:5], t)[..., 2:].sum()*sc[0]
        true = 40*actual[2:].sum()
        water_cases.append({"water_mm": water, "reference_uvi": float(true),
                            "inferred_uvi": float(estimate), "relative_error": float(estimate/true-1)})
    report = {"kind": "numerical RT qualification, NOT observational validation", "seed": seed,
              "table_sha256": table.sha256, "table_configuration": table.metadata,
              "columns": count, "uvi_ge1_columns": int(mask.sum()),
              "forward_max_abs_uvi": float(np.max(abs(estimated-uvi))),
              "forward_relative_p95_uvi_ge1": float(np.quantile(abs(relative), .95)),
              "forward_relative_max_uvi_ge1": float(np.max(abs(relative))),
              "inversion_relative_p95_uvi_ge1": float(np.quantile(abs(inverse_relative), .95)),
              "inversion_relative_max_uvi_ge1": float(np.max(abs(inverse_relative))),
              "different_albedo_inversion_p95_uvi_ge1": float(np.quantile(abs(paired_relative), .95)),
              "different_albedo_inversion_max_uvi_ge1": float(np.max(abs(paired_relative))),
              "spectral_stream_convergence": resolution,
              "fixed_water_sensitivity_examples": water_cases,
              "cases": [{"point": p.tolist(), "reference_uvi": float(u), "table_uvi": float(v),
                         "sw_inferred_uvi": float(r), "inferred_tau": float(t), "flag": int(f),
                         "separate_sw_albedo": float(sa), "different_albedo_inferred_uvi": float(pu)}
                        for p, u, v, r, t, f, sa, pu in zip(points, uvi, estimated, reconstructed, tau, flags,
                                                           sw_points[:, 4], paired_uvi)]}
    # Engineering interpolation budget, not an observational service SLA.
    report["numerical_gates"] = {"p95_relative_limit": .05, "maximum_relative_limit": .10,
                                  "scope": "UVI>=1, forward and SW-inversion paths including different UV/SW albedos"}
    report["numerical_gate_passed"] = bool(
        max(report["forward_relative_p95_uvi_ge1"], report["inversion_relative_p95_uvi_ge1"],
            report["different_albedo_inversion_p95_uvi_ge1"]) <= .05
        and max(report["forward_relative_max_uvi_ge1"], report["inversion_relative_max_uvi_ge1"],
                report["different_albedo_inversion_max_uvi_ge1"]) <= .10)
    Path(output).write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--lib", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate(RadiationTable(args.table), args.lib, args.cache, args.output)
    raise SystemExit(0 if report["numerical_gate_passed"] else 1)
