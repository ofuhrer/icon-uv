import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
import eccodes as ec

from icon_uv.data import interval_radiation, load_cams, write_netcdf, cams_request, fetch_cams
from icon_uv.products import POI, compute_grid, compute_pois, compare_observations
from icon_uv.radiation import AXES, RadiationTable, erythema, solar_geometry
from icon_uv.check_grid import check_grid
from icon_uv.compare_public_uv import compare as compare_public_uv


@pytest.fixture
def table(tmp_path):
    axes = dict(sza=[0, 89], ozone_du=[200, 500], pressure_pa=[50000, 105000],
                aod550=[0, 1], albedo=[0, .85], tau550=[0, 1, 5, 150])
    z, o, p, a, al, tau = np.meshgrid(*(axes[k] for k in AXES), indexing="ij")
    base = np.exp(-z/30) * (o/320)**-1.2 * np.exp((85000-p)/200000-a*.4+al*.5)
    flux = np.stack([800*base/(1+tau), 100*base/(1+tau)**.4,
                     .08*base/(1+tau), .04*base/(1+tau)**.4], axis=-1)
    path = tmp_path/"synthetic.npz"
    np.savez_compressed(path, **axes, flux=flux, metadata=json.dumps({"test_only": True}))
    return RadiationTable(path)


@pytest.fixture
def icon():
    times = np.array(["2026-09-06T11:30", "2026-09-06T12:30"], dtype="datetime64[ns]")
    shape = (2, 2)
    ds = xr.Dataset({"pressure_pa": (("time", "cell"), np.full(shape, 95000.)),
                     "sw_down": (("time", "cell"), np.full(shape, 300.)),
                     "sw_albedo": (("time", "cell"), np.full(shape, .15)),
                     "snow_fraction": (("time", "cell"), np.zeros(shape)),
                     "time_bounds": (("time", "bounds"), np.column_stack([times-np.timedelta64(30, "m"), times+np.timedelta64(30, "m")]))},
                    coords={"time": times, "cell": [13, 29], "latitude": ("cell", [46.8, 47.]),
                            "longitude": ("cell", [7., 8.]), "altitude_m": ("cell", [500., 800.])},
                    attrs={"forecast_reference_time": "2026-09-05T12:00:00Z", "grid_uuid": "test"})
    for k, u in (("pressure_pa", "Pa"), ("sw_down", "W m-2"), ("sw_albedo", "1"), ("snow_fraction", "1")):
        ds[k].attrs["units"] = u
    ds.time.attrs["bounds"] = "time_bounds"
    return ds


@pytest.fixture
def cams():
    shape = (2, 2, 2)
    ds = xr.Dataset({"ozone_du": (("time", "latitude", "longitude"), np.full(shape, 310.)),
                     "aod550": (("time", "latitude", "longitude"), np.full(shape, .12))},
                    coords={"time": np.array(["2026-09-06T10:00", "2026-09-06T13:00"], dtype="datetime64[ns]"),
                            "latitude": [45., 49.], "longitude": [5., 11.]},
                    attrs={"forecast_reference_time": "2026-09-05T00:00:00Z", "source": "synthetic test only"})
    ds.ozone_du.attrs["units"] = "DU"
    ds.aod550.attrs["units"] = "1"
    return ds


def test_erythema():
    np.testing.assert_allclose(erythema([249, 250, 298, 310, 340, 401]),
                               [0, 1, 1, 10**(-1.128), .001, 0])


def test_no_spectral_band_mean_shortcut():
    w = np.arange(295, 306, .5)
    spectrum = np.exp((w-295)/3)
    exact = np.trapezoid(spectrum*erythema(w), w)
    wrong = np.trapezoid(spectrum, w)*np.trapezoid(erythema(w), w)/(w[-1]-w[0])
    assert abs(exact-wrong)/exact > .1


def test_solar_broadcast_and_night():
    t = np.array(["2026-03-20T00:00", "2026-03-20T12:00"], dtype="datetime64[ns]")
    z, az, d = solar_geometry(t[:, None], np.array([0., 47.])[None, :], 0.)
    assert z.shape == az.shape == (2, 2)
    assert z[0, 0] > 170 and z[1, 0] < 3
    assert np.all((d > .96) & (d < 1.04))
    with pytest.raises(ValueError):
        solar_geometry(["NaT"], 47, 8)


def test_interval_mean_and_packing():
    actual = np.array([[100, 0], [200, 0], [300, 0.]])
    means = np.cumsum(actual, axis=0)/np.arange(1, 4)[:, None]
    np.testing.assert_allclose(interval_radiation([1, 2, 3], means, [0, 0, 0]), actual[1:])
    assert interval_radiation([100, 101], [[1], [.989]], [.001, .001])[0, 0] == 0
    with pytest.raises(ValueError):
        interval_radiation([1, 3], [[10], [10]], [0, 0])
    with pytest.raises(ValueError):
        interval_radiation([1, 2], [[100], [0]], [0, 0])


def test_table_knots_night_bounds(table):
    i = (1, 0, 1, 0, 1, 2)
    p = [table.axes[k][j] for k, j in zip(AXES, i)]
    np.testing.assert_allclose(table.at(*p), table.values[i], rtol=1e-12)
    assert np.all(table.at(110, 300, 90000, .1, .1, 2) == 0)
    with pytest.raises(ValueError, match="ozone_du"):
        table.at(45, 190, 90000, .1, .1, 0)
    with pytest.raises(ValueError):
        table.at(np.nan, 300, 90000, .1, .1, 0)


def test_cloud_roundtrip(table):
    z = np.array([[30., 55], [40, 60], [50, 65], [60, 70]])
    o, p, a, al = np.array([310., 340]), np.array([95000., 70000]), np.array([.1, .2]), np.array([.05, .6])
    expected = np.array([3., 25.])
    forcing = table.at(z, o, p, a, al, expected)[..., :2].sum(axis=-1).mean(axis=0)
    t, scale, flags = table.cloud(z, np.ones((4, 1)), o, p, a, al, forcing)
    np.testing.assert_allclose(t, expected, rtol=2e-6)
    np.testing.assert_array_equal(scale, 1)
    np.testing.assert_array_equal(flags, 0)


def test_cloud_exceptions(table):
    z = np.full((4, 3), 40.)
    o, p, a, al = np.full(3, 300.), np.full(3, 90000.), np.full(3, .1), np.full(3, .1)
    forcing = np.array([2000., 0., 0.])
    z[:, 2] = 110
    tau, scale, flags = table.cloud(z, 1., o, p, a, al, forcing)
    assert flags[0] & 1 and flags[1] & 2 and flags[2] & 4
    assert tau[0] == 0 and tau[1] == 150 and scale[1] == 0


def test_rejects_night_shortwave(table):
    with pytest.raises(ValueError, match="at night"):
        table.cloud(np.full((4, 1), 110.), 1., np.array([300.]), np.array([90000.]),
                    np.array([.1]), np.array([.1]), np.array([100.]))


def test_nonmonotone_cloud_first_branch(table, tmp_path):
    flux = np.empty_like(table.values)
    levels = np.array([100., 80., 90., 1.])
    for i, fraction in enumerate((.4, .6, .0004, .0006)):
        flux[..., i] = levels*fraction
    path = tmp_path/"nonmonotone.npz"
    np.savez_compressed(path, **table.axes, flux=flux, metadata="{}")
    other = RadiationTable(path)
    z, o, p, a, al = np.array([[40.]]), np.array([300.]), np.array([90000.]), np.array([.1]), np.array([.1])
    tau, scale, flags = other.cloud(z, 1., o, p, a, al, np.array([85.]))
    assert flags[0] & 8 and 0 < tau[0] < 1 and scale[0] == 1
    np.testing.assert_allclose(other.at(z, o, p, a, al, tau)[..., :2].sum(), 85., rtol=1e-6)


def test_nonmonotone_tail_cannot_override_valid_branch(table, tmp_path):
    flux = np.empty_like(table.values)
    for i, fraction in enumerate((.4, .6, .0004, .0006)):
        flux[..., i] = np.array([100., 80., 30., 200.])*fraction
    path = tmp_path/"rising-tail.npz"
    np.savez_compressed(path, **table.axes, flux=flux, metadata="{}")
    other = RadiationTable(path)
    z = np.full((1, 3), 40.)
    o, p, a, al = np.full(3, 300.), np.full(3, 90000.), np.full(3, .1), np.full(3, .1)
    tau, scale, flags = other.cloud(z, 1., o, p, a, al, np.array([90., 10., 150.]))
    assert 0 < tau[0] < 1 and scale[0] == 1 and flags[0] == 8
    assert tau[1] == 5 and scale[1] == pytest.approx(1/3) and flags[1] == 10
    assert tau[2] == 0 and scale[2] == pytest.approx(1.5) and flags[2] == 9


def test_low_sun_is_flagged(table):
    z = np.array([[80.]])
    tau, scale, flags = table.cloud(z, 1., np.array([300.]), np.array([90000.]),
                                    np.array([.1]), np.array([.1]), np.array([20.]))
    assert flags[0] & 64


def test_rejected_prototype_table_cannot_be_loaded(table, tmp_path):
    path = tmp_path/"rejected.npz"
    np.savez_compressed(path, **table.axes, flux=table.values, metadata='{"schema": 1}')
    with pytest.raises(ValueError, match="Rejected prototype"):
        RadiationTable(path)


def test_packaged_table_solar_energy_bound():
    table = RadiationTable()
    z = table.axes["sza"][:, None, None, None, None, None]
    albedo = table.axes["albedo"][None, None, None, None, :, None]
    net_down_bound = table.values[..., :2].sum(axis=-1)*(1-albedo)
    assert np.all(net_down_bound <= 1400*np.cos(np.deg2rad(z))+1e-3)
    assert table.metadata["schema"] >= 2


def test_compute_chunking_and_roundtrip(icon, cams, table, tmp_path):
    a = compute_grid(icon, cams, table, chunk_size=1)
    b = compute_grid(icon, cams, table, chunk_size=2)
    np.testing.assert_allclose(a.uvi, b.uvi)
    np.testing.assert_allclose(a.uvi, 40*(a.erythemal_direct+a.erythemal_diffuse), rtol=1e-6)
    assert np.all(a.uvi_sample_max >= a.uvi)
    write_netcdf(a, tmp_path/"out.nc")
    with xr.open_dataset(tmp_path/"out.nc") as reopened:
        np.testing.assert_allclose(a.uvi, reopened.uvi)
        np.testing.assert_array_equal(a.time_bounds, reopened.time_bounds)
        assert reopened.quality_flag.dtype == np.uint16


def test_grid_integrity_and_sw_reconstruction(icon, cams, table):
    grid = compute_grid(icon, cams, table)
    grid.attrs["bbox"] = json.dumps([5., 45., 11., 49.])
    report = check_grid(grid, table)
    assert report["passed"] and report["maximum_sw_reconstruction_residual_w_m2"] < .001
    grid.uvi.values[0, 0] += 1
    with pytest.raises(ValueError, match="component identity"):
        check_grid(grid, table)


def test_public_observation_pairs_are_explicitly_unqualified(icon, cams, table):
    grid = compute_grid(icon, cams, table)
    grid.attrs["bbox"] = json.dumps([5., 45., 11., 49.])
    values = {"site": {"uve": {"unit": "UV-Index", "ts": ["2026-09-06T11:15:00+0000", "2026-09-06T11:45:00+0000"],
                                "measurement": [2., 4.]}}}
    sites = [{"name": "site", "latitude": 46.8, "longitude": 7., "altitude": 500.}]
    report = compare_public_uv(grid, values, sites)
    assert report["sites"]["site"]["matched_hours"] == 1
    assert report["sites"]["site"]["pairs"][0]["reported_pair_mean_uvi"] == 3
    assert "no per-value QC" in report["qc_status"]
    missing = {"site": {"uve": {**values["site"]["uve"], "ts": values["site"]["uve"]["ts"][:1],
                                "measurement": [2.]}}}
    assert compare_public_uv(grid, missing, sites)["sites"]["site"]["matched_hours"] == 0
    values["site"]["uve"]["ts"][1] = values["site"]["uve"]["ts"][0]
    with pytest.raises(ValueError, match="Duplicate"):
        compare_public_uv(grid, values, sites)


def test_cams_contract_and_units(cams, tmp_path):
    path = tmp_path/"cams.nc"
    cams.to_netcdf(path)
    assert load_cams(path).sizes == cams.sizes
    cams.ozone_du.attrs["units"] = "kg m-2"
    cams.to_netcdf(path)
    with pytest.raises(ValueError, match="ozone_du"):
        load_cams(path)


def test_cams_lookahead_and_coverage(icon, cams, table):
    cams.attrs["forecast_reference_time"] = "2026-09-06T00:00:00Z"
    with pytest.raises(ValueError, match="look-ahead"):
        compute_grid(icon, cams, table)
    cams.attrs["forecast_reference_time"] = "2026-09-05T00:00:00Z"
    cams = cams.assign_coords(longitude=[9., 10.])
    with pytest.raises(ValueError):
        compute_grid(icon, cams, table)


def test_cams_request():
    q = cams_request("2026-09-05T00:00:00Z", [21, 24])
    assert q["variable"] == ["total_column_ozone", "total_aerosol_optical_depth_550nm"]
    assert q["area"] == [50., 4., 44., 13.]
    with pytest.raises(ValueError):
        cams_request("2026-09-05T06:00:00Z", [0])
    with pytest.raises(ValueError):
        cams_request("2026-09-05T00:00:00Z", [3, 0])


def test_poi_requires_own_geometry():
    with pytest.raises(TypeError):
        POI("incomplete", 47, 8, 500)
    with pytest.raises(ValueError):
        POI("bad", 47, 8, 500, (0, 0, np.nan, 0), .05)


def test_poi_flat_horizon_and_screen(icon, cams, table):
    grid = compute_grid(icon, cams, table)
    flat = POI("flat", 46.8, 7., 500, (0.,)*36, .05)
    wall = POI("wall", 46.8, 7., 500, (90.,)*36, .05)
    higher = POI("higher", 46.8, 7., 1000, (0.,)*36, .05)
    result = compute_pois(grid, [flat, wall, higher], table)
    np.testing.assert_allclose(result.uvi[:, 0], grid.uvi[:, 0], rtol=1e-6)
    np.testing.assert_allclose(result.terrain_screened_uvi[:, 0], result.uvi[:, 0])
    assert np.all(result.terrain_screened_uvi[:, 1] < 1e-20)
    assert np.all(result.pressure_pa[:, 2] < result.pressure_pa[:, 0])
    assert np.all(result.quality_flag.values & 16)
    with pytest.raises(ValueError, match="too far"):
        compute_pois(grid, [POI("far", 48, 10, 500, (0.,)*4, .05)], table)


def test_poi_rejects_changed_radiation_table(icon, cams, table):
    grid = compute_grid(icon, cams, table)
    grid.attrs["radiation_table_sha256"] = "old-table"
    with pytest.raises(ValueError, match="table differs"):
        compute_pois(grid, [POI("site", 47, 8, 500, (0.,)*4, .05)], table)


def test_observation_matching(icon, cams, table):
    f = compute_pois(compute_grid(icon, cams, table), [POI("site", 46.8, 7, 500, (0.,)*4, .05)], table)
    o = f[["uvi", "time_bounds"]].copy(deep=True)
    o["uvi"] = o.uvi-1
    o.uvi.attrs["units"] = "1"
    o["qc_good"] = (("time", "poi"), np.array([[True], [False]]))
    m = compare_observations(f, o)
    assert m["samples"] == 1 and m["bias_uvi"] == pytest.approx(1)
    o["time_bounds"] = o.time_bounds+np.timedelta64(1, "m")
    with pytest.raises(ValueError, match="bounds"):
        compare_observations(f, o)


def test_gap_rejected(icon, cams, table):
    icon.time_bounds.values[1] += np.timedelta64(1, "h")
    with pytest.raises(ValueError, match="contiguous"):
        compute_grid(icon, cams, table)


def test_api_rejects_composition_units(icon, cams, table):
    cams.ozone_du.attrs["units"] = "kg m-2"
    with pytest.raises(ValueError, match="CAMS ozone_du"):
        compute_grid(icon, cams, table)


def test_api_rejects_coordinates(icon, cams, table):
    icon.latitude.values[0] = 100
    with pytest.raises(ValueError, match="geographic"):
        compute_grid(icon, cams, table)


def test_duplicate_cells(icon, cams, table):
    icon = icon.assign_coords(cell=[13, 13])
    with pytest.raises(ValueError, match="Duplicate"):
        compute_grid(icon, cams, table)


@pytest.fixture
def cams_grib(tmp_path):
    path = tmp_path/"synthetic-cams.grib"
    with path.open("wb") as f:
        for lead in (33, 36, 39):
            for parameter, value in ((206, .0064245), (210207, .15)):
                g = ec.codes_grib_new_from_samples("regular_ll_sfc_grib1")
                try:
                    for key, val in {"Ni": 2, "Nj": 2, "latitudeOfFirstGridPointInDegrees": 48,
                                     "latitudeOfLastGridPointInDegrees": 46, "longitudeOfFirstGridPointInDegrees": 6,
                                     "longitudeOfLastGridPointInDegrees": 8, "iDirectionIncrementInDegrees": 2,
                                     "jDirectionIncrementInDegrees": 2, "dataDate": 20260905,
                                     "dataTime": 0, "step": lead, "paramId": parameter}.items():
                        ec.codes_set(g, key, val)
                    ec.codes_set_values(g, np.full(4, value))
                    ec.codes_write(g, f)
                finally:
                    ec.codes_release(g)
    return path


@pytest.fixture
def ads_download(monkeypatch, cams_grib):
    calls = []

    def retrieve(dataset, request, target):
        calls.append((dataset, request))
        Path(target).write_bytes(cams_grib.read_bytes())

    monkeypatch.setitem(sys.modules, "cdsapi", SimpleNamespace(
        Client=lambda **kwargs: SimpleNamespace(retrieve=retrieve)))
    return calls


def test_fetch_cams_normalized_netcdf(tmp_path, cams_grib, ads_download):
    path = tmp_path/"output"/"cams.nc"
    fetch_cams("2026-09-05T00:00:00Z", [33, 36, 39], path)
    ds = load_cams(path)
    assert ds.sizes == {"time": 3, "latitude": 2, "longitude": 2}
    np.testing.assert_allclose(ds.ozone_du, 300., rtol=1e-6)
    np.testing.assert_allclose(ds.aod550, .15, rtol=1e-6)
    assert list(ds.latitude.values) == [46, 48]
    assert ds.ozone_du.attrs["units"] == "DU"
    assert ds.aod550.attrs["units"] == "1"
    assert ds.ozone_du.dtype == np.float32
    assert ds.ozone_du.encoding["zlib"]
    assert ds.aod550.encoding["zlib"]
    assert ds.attrs["source_grib_sha256"] == hashlib.sha256(cams_grib.read_bytes()).hexdigest()
    assert ds.attrs["input_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert ds.attrs["source"] == ads_download[0][0]
    assert json.loads(ds.attrs["retrieval_request"]) == ads_download[0][1]
    np.testing.assert_array_equal(ds.time, np.array([
        "2026-09-06T09:00", "2026-09-06T12:00", "2026-09-06T15:00"], dtype="datetime64[ns]"))
    assert list(path.parent.iterdir()) == [path]


def test_load_cams_requires_netcdf(cams_grib):
    with pytest.raises(OSError):
        load_cams(cams_grib)


@pytest.mark.parametrize("failure", ["cycle", "times", "missing_aod", "download"])
def test_fetch_cams_failure_preserves_output(tmp_path, cams_grib, ads_download, monkeypatch, failure):
    path = tmp_path/"output"/"cams.nc"
    path.parent.mkdir()
    path.write_bytes(b"previous publication")
    reference, leads = "2026-09-05T00:00:00Z", [33, 36, 39]
    error, message = ValueError, "cycle/times"
    if failure == "cycle":
        reference = "2026-09-05T12:00:00Z"
    elif failure == "times":
        leads = [33, 36]
    elif failure == "missing_aod":
        # Each lead has ozone followed by AOD; retaining the first message
        # simulates a truncated but readable response.
        with cams_grib.open("rb") as f:
            g = ec.codes_grib_new_from_file(f)
            try:
                ozone_only = ec.codes_get_message(g)
            finally:
                ec.codes_release(g)
        cams_grib.write_bytes(ozone_only)
        message = "matching ozone/AOD"
    else:
        def fail(dataset, request, target):
            Path(target).write_bytes(b"partial download")
            raise OSError("connection lost")
        monkeypatch.setitem(sys.modules, "cdsapi", SimpleNamespace(
            Client=lambda **kwargs: SimpleNamespace(retrieve=fail)))
        error, message = OSError, "connection lost"
    with pytest.raises(error, match=message):
        fetch_cams(reference, leads, path)
    assert path.read_bytes() == b"previous publication"
    assert list(path.parent.iterdir()) == [path]


def test_cli_cams_netcdf_to_uv(tmp_path, ads_download, icon, table, monkeypatch):
    from icon_uv import cli

    cams_path, icon_path, uv_path = (tmp_path/name for name in ("cams.nc", "icon.nc", "uv.nc"))
    monkeypatch.setattr(sys, "argv", ["icon-uv", "fetch-cams", "--reference", "2026-09-05T00:00:00Z",
                                     "--first-lead", "33", "--last-lead", "39", "--output", str(cams_path)])
    cli.main()
    write_netcdf(icon, icon_path)
    monkeypatch.setattr(cli, "RadiationTable", lambda path: table)
    monkeypatch.setattr(sys, "argv", ["icon-uv", "run", "--icon", str(icon_path),
                                     "--cams", str(cams_path), "--output", str(uv_path)])
    cli.main()
    # Independent normalized composition values, avoiding a GRIB reader in run.
    expected_cams = load_cams(cams_path).copy(deep=True)
    expected_cams["ozone_du"][:] = 300.
    expected_cams["aod550"][:] = .15
    expected = compute_grid(icon, expected_cams, table)
    with xr.open_dataset(uv_path) as result:
        for name in ("uvi", "clear_sky_uvi"):
            assert np.isfinite(result[name]).all()
            np.testing.assert_allclose(result[name], expected[name], rtol=1e-6)


def test_failed_publication_preserves_existing(icon, tmp_path, monkeypatch):
    path = tmp_path/"product.nc"
    path.write_bytes(b"previous publication")

    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail)
    with pytest.raises(OSError):
        write_netcdf(icon, path)
    assert path.read_bytes() == b"previous publication"
    assert list(tmp_path.iterdir()) == [path]
