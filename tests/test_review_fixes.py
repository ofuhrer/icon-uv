"""Regression coverage for the September 2026 review findings."""
import json
import shutil
import traceback

import numpy as np
import pytest
import requests
import xarray as xr

from icon_uv import build_table, data
from icon_uv.products import compare_observations
from icon_uv.radiation import solar_geometry


@pytest.fixture
def paired_uv():
    times = np.array(["2026-09-05T11:30", "2026-09-05T12:30"], dtype="datetime64[ns]")
    forecast = xr.Dataset(
        {"uvi": (("time", "poi"), [[3., 7.], [4., 8.]]),
         "time_bounds": (("time", "bounds"), np.column_stack([
             times-np.timedelta64(30, "m"), times+np.timedelta64(30, "m")]))},
        coords={"time": times, "poi": ["A", "B"]})
    forecast.uvi.attrs["units"] = "1"
    observations = forecast.copy(deep=True)
    observations["qc_good"] = (("time", "poi"), np.ones((2, 2), bool))
    return forecast, observations


@pytest.mark.parametrize("side", [0, 1])
def test_observation_rejects_cartesian_station_pairing(paired_uv, side):
    pair = list(paired_uv)
    pair[side] = pair[side].rename(poi="station")
    with pytest.raises(ValueError, match=r"uvi\(time,poi\)"):
        compare_observations(*pair)


def test_observation_rejects_broadcast_qc(paired_uv):
    forecast, observations = paired_uv
    observations["qc_good"] = ("time", [True, False])
    with pytest.raises(ValueError, match="qc_good"):
        compare_observations(forecast, observations)


@pytest.mark.parametrize("dim", ["time", "poi"])
@pytest.mark.parametrize("side", [0, 1])
def test_observation_requires_unique_named_coordinates(paired_uv, dim, side):
    pair = list(paired_uv)
    pair[side] = pair[side].assign_coords({dim: [pair[side][dim].values[0]]*2})
    with pytest.raises(ValueError, match="unique"):
        compare_observations(*pair)
    pair = list(paired_uv)
    pair[side] = pair[side].drop_vars(dim)
    with pytest.raises(ValueError, match="named"):
        compare_observations(*pair)


@pytest.mark.parametrize("problem", ["missing", "shape", "nat", "nonhourly", "midpoint"])
def test_observation_rejects_invalid_interval_bounds(paired_uv, problem):
    forecast, observations = paired_uv
    if problem == "missing":
        observations = observations.drop_vars("time_bounds")
    elif problem == "shape":
        observations = observations.isel(bounds=[0])
    elif problem == "nat":
        observations.time_bounds.values[0, 0] = np.datetime64("NaT")
    elif problem == "nonhourly":
        observations.time_bounds.values[:, 1] += np.timedelta64(1, "h")
    else:
        observations = observations.assign_coords(time=observations.time+np.timedelta64(1, "m"))
    with pytest.raises(ValueError, match="bounds"):
        compare_observations(forecast, observations)


def test_observation_inner_match_uses_site_names_and_qc(paired_uv):
    forecast, observations = paired_uv
    # Reorder sites and time; partial coverage still uses identifiers, not position.
    observations = observations.isel(time=[1], poi=[1, 0])
    observations.uvi.values[0] = [10., 4.]
    observations.qc_good.values[0] = [False, True]
    report = compare_observations(forecast, observations)
    assert report["samples"] == 1
    assert report["mae_uvi"] == 0
    observations.qc_good.values[:] = True
    report = compare_observations(forecast, observations)
    assert report["samples"] == 2
    assert report["mae_uvi"] == 1


@pytest.mark.parametrize("body", [None, {"forecast:variable": "ASOD_S"}])
@pytest.mark.parametrize("error", [requests.ConnectionError, requests.Timeout, requests.TooManyRedirects])
def test_transport_errors_do_not_expose_signed_urls(monkeypatch, body, error):
    url = "https://example.test/asset?signature=original-secret#fragment-secret"

    def fail(*args, **kwargs):
        raise error("Failed at https://redirect.test/asset?signature=redirect-secret")

    monkeypatch.setattr(data.requests, "get" if body is None else "post", fail)
    with pytest.raises(RuntimeError) as caught:
        data._request(url, body)
    rendered = "".join(traceback.format_exception(caught.value))
    for secret in ("original-secret", "fragment-secret", "redirect-secret"):
        assert secret not in rendered
    assert str(caught.value) == f"{error.__name__} retrieving https://example.test/asset"


@pytest.mark.parametrize("suffix", ["?signature=query-secret#fragment-secret", "#fragment-secret"])
def test_http_errors_hide_queries_and_fragments(monkeypatch, suffix):
    response = requests.Response()
    response.status_code = 403
    monkeypatch.setattr(data.requests, "get", lambda *a, **kw: response)
    with pytest.raises(RuntimeError, match="HTTP 403") as caught:
        data._request("https://example.test/asset"+suffix)
    assert str(caught.value) == "HTTP 403 retrieving https://example.test/asset"


@pytest.mark.parametrize("body", [None, {}])
def test_request_success_preserves_signed_request(monkeypatch, body):
    response = requests.Response()
    response.status_code = 200
    url = "https://example.test/asset?signature=required"
    calls = []

    def succeed(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr(data.requests, "get" if body is None else "post", succeed)
    assert data._request(url, body) is response
    assert calls == [((url,), dict(timeout=120, **({} if body is None else {"json": body})))]


def test_solar_geometry_mixed_leap_and_common_years():
    # NOAA equations evaluated with 366 days in 2028 and 365 in 2026.
    times = np.array(["2026-09-22T11:30", "2028-09-22T11:30"], dtype="datetime64[ns]")
    z, az, distance = solar_geometry(times[:, None], np.array([46.8])[None, :], 9.83)
    np.testing.assert_allclose(z[:, 0], [46.296423022224694, 46.40521292143858], atol=1e-9, rtol=0)
    scalar = solar_geometry(times[1], 46.8, 9.83)
    np.testing.assert_allclose([v[1, 0] for v in (z, az, distance)], scalar)


@pytest.fixture
def solver_installation(tmp_path, monkeypatch):
    lib = tmp_path / "solver"
    (lib / "bin").mkdir(parents=True)
    (lib / "data/atmmod").mkdir(parents=True)
    binary = lib / "bin/uvspec"
    binary.write_bytes(b"test binary v1")
    binary.chmod(0o755)
    (lib / "data/atmmod/afglms.dat").write_bytes(b"test atmosphere v1")
    computed = []

    def calculate(lib, point, **kwargs):
        computed.append((lib, point, kwargs))
        return np.array([100., 20., .05, .02])

    monkeypatch.setattr(build_table, "_calculate_reference", calculate)
    return lib, tmp_path / "cache", computed


POINT = [35., 300., 95000., .15, .05, 0.]


def test_reference_cache_reuses_after_relocation(solver_installation, tmp_path):
    lib, cache, computed = solver_installation
    original = build_table.ReferenceSolver(lib, cache)
    expected = original(POINT)
    assert original.cache_info() == {"hits": 0, "computed": 1}
    relocated = tmp_path / "relocated"
    shutil.copytree(lib, relocated)
    warm = build_table.ReferenceSolver(relocated, cache)
    np.testing.assert_array_equal(warm(POINT), expected)
    assert warm.provenance == original.provenance
    assert warm.cache_info() == {"hits": 1, "computed": 0}
    assert len(computed) == 1
    assert json.loads((warm.directory / "manifest.json").read_text()) == warm.provenance


@pytest.mark.parametrize("changed", ["binary", "data", "implementation", "erythema", "settings"])
def test_reference_cache_invalidates_changes(solver_installation, monkeypatch, changed):
    lib, cache, computed = solver_installation
    original = build_table.ReferenceSolver(lib, cache)
    original(POINT)
    if changed == "binary":
        (lib / "bin/uvspec").write_bytes(b"test binary v2")
    elif changed == "data":
        (lib / "data/atmmod/afglms.dat").write_bytes(b"test atmosphere v2")
    elif changed in ("implementation", "erythema"):
        # Simulate changed packaged reference source without editing the checkout.
        digest = build_table._file_sha256
        source = build_table.__file__ if changed == "implementation" else build_table.radiation.__file__
        monkeypatch.setattr(build_table, "_file_sha256", lambda p: "changed-source" if str(p) == source else digest(p))
    refreshed = build_table.ReferenceSolver(lib, cache)
    refreshed(POINT, **({"water": 40} if changed == "settings" else {}))
    assert len(computed) == 2
    assert refreshed.cache_info() == {"hits": 0, "computed": 1}
    assert original.directory.exists()


def test_reference_does_not_trust_legacy_cache_or_missing_solver(solver_installation):
    lib, cache, computed = solver_installation
    config = dict(build_table.CONFIG, spacing_nm=.5, streams=8, water_mm=20)
    key = build_table.hashlib.sha256(json.dumps([config, POINT], sort_keys=True).encode()).hexdigest()
    cache.mkdir()
    old = cache / (key + ".npz")
    np.savez_compressed(old, flux=[999., 999., 999., 999.])
    expected = build_table.reference(lib, POINT, cache)
    assert expected[0] == 100
    assert old.exists()
    with pytest.raises(ValueError, match="executable"):
        build_table.reference(lib / "missing", POINT, cache)
    (lib / "bin/uvspec").unlink()
    with pytest.raises(ValueError, match="executable"):
        build_table.reference(lib, POINT, cache)
