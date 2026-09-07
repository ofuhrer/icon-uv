"""Regression against independent, higher-stream liquid-cloud solver columns.

libRadtran 2.0.6, plane-parallel DISORT 16 streams (runtime LUT uses 8),
AFGL midlatitude summer, water 20 mm, ozone 320 DU, 500 m surface,
AOD550 0.1 / Angstrom 1.3 / SSA 0.95 / g 0.7, gray albedo 0.05,
liquid cloud 1-2 km above surface, radius 10 um, Hu optical properties.
SW uses Kato2; UV uses 0.5 nm sampling, atlas_plus_modtran, and the
erythemal action spectrum. Fluxes are at 1 AU on a horizontal surface.

These fixed references protect the central cloud-conversion calculation;
they do not validate broken clouds, ice/snow or actual weather forecasts.
The wider cloud stress experiment is summarized in docs/validation.md.
"""
import numpy as np
import pytest

from icon_uv.radiation import RadiationTable

# SZA, reference cloud tau550, reference SW (W/m2), reference UVI.
REFERENCE_COLUMNS = [
    (30, 2, 808.9730400000001, 6.91031697492582),
    (30, 20, 325.23720004880704, 3.5247201038879705),
    (30, 100, 79.91624, 1.0542939501726183),
    (45, 2, 607.64685, 4.005154384919602),
    (45, 20, 234.89210000019304, 2.0172121823384432),
    (45, 100, 57.82194, 0.6088829039752413),
    (65, 2, 281.50345599999997, 1.0899084104243681),
    (65, 20, 106.0379, 0.5473687121301305),
    (65, 100, 26.20001, 0.16758346456442627),
]


@pytest.mark.parametrize('sza,reference_tau,shortwave,reference_uvi', REFERENCE_COLUMNS)
def test_liquid_cloud_conversion_against_direct_solver(sza, reference_tau, shortwave, reference_uvi):
    table = RadiationTable()
    pressure = 101325*np.exp(-500/8434)
    tau, scale, flags = table.cloud(
        np.array([[sza]]), np.ones((1, 1)), np.array([320.]),
        np.array([pressure]), np.array([.1]), np.array([.05]), np.array([shortwave]))
    flux = table.at(sza, 320, pressure, .1, .05, tau[0])*scale[0]
    # Numerical inversion closes SW independently of the UV reference check.
    assert abs(flux[:2].sum()-shortwave) < .001
    assert abs(40*flux[2:].sum()-reference_uvi) < .15
    assert np.isfinite(tau[0]) and 0 <= tau[0] <= 150
