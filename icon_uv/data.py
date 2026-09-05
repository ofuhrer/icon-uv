"""Small explicit data adapters: public ICON STAC and CAMS ADS GRIB/NetCDF.

No account creation, embedded credentials, scraping or implicit provider fallback.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import tempfile

import eccodes as ec
import numpy as np
import requests
import xarray as xr

STAC = "https://data.geo.admin.ch/api/stac/v1"
COLLECTION = "ch.meteoschweiz.ogd-forecasting-icon-ch2"
BBOX = (5.3, 45.2, 11.2, 48.4)  # west, south, east, north
CAMS_DATASET = "cams-global-atmospheric-composition-forecasts"
DU_KG_M2 = 2.1415e-5


def utc(value):
    t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Forecast reference must include UTC offset")
    return t.astimezone(timezone.utc)


def validate_bbox(bbox):
    w, s, e, n = bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("bbox must be west,south,east,north in degrees")


def _request(url, body=None):
    r = requests.get(url, timeout=120) if body is None else requests.post(url, json=body, timeout=120)
    # Do not print signed query strings in error messages or persist them.
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} retrieving {url.split('?')[0]}")
    return r


def grib_messages(path):
    with Path(path).open("rb") as f:
        while (g := ec.codes_grib_new_from_file(f)) is not None:
            try:
                meta = {}
                for k in ("shortName", "units", "stepType", "startStep", "endStep", "stepUnits",
                          "dataDate", "dataTime", "validityDate", "validityTime", "paramId",
                          "uuidOfHGrid", "perturbationNumber", "packingError", "gridType"):
                    try:
                        meta[k] = ec.codes_get(g, k)
                    except ec.CodesInternalError:
                        pass
                values = ec.codes_get_values(g)
                if ec.codes_get(g, "bitmapPresent"):
                    bitmap = ec.codes_get_array(g, "bitmap")
                    values[bitmap == 0] = np.nan
                coords = None
                if meta["gridType"] == "regular_ll":
                    coords = (ec.codes_get_array(g, "latitudes"), ec.codes_get_array(g, "longitudes"))
                yield meta, values, coords
            finally:
                ec.codes_release(g)


def _decode_bytes(raw):
    # ecCodes file reader handles multi-message files consistently across versions.
    with tempfile.NamedTemporaryFile(suffix=".grib") as f:
        f.write(raw)
        f.flush()
        return list(grib_messages(f.name))


def interval_radiation(leads, means, errors):
    t = np.asarray(leads, float)
    a = np.asarray(means, float)
    err = np.asarray(errors, float)
    if len(t) < 2 or a.shape[0] != len(t) or err.shape != t.shape:
        raise ValueError("Invalid radiation series shape")
    if np.any(t < 0) or not np.all(np.diff(t) == 1) or not np.all(np.isfinite(a)):
        raise ValueError("Missing hour, reset, duplicate or nonfinite radiation")
    shape = (-1,) + (1,)*(a.ndim-1)
    flux = np.diff(t.reshape(shape)*a, axis=0)
    tolerance = (t[1:]*err[1:]+t[:-1]*err[:-1]+1e-6).reshape(shape)
    if np.any(flux < -tolerance):
        raise ValueError("Negative hourly energy beyond GRIB packing error")
    return np.maximum(flux, 0)


def fetch_icon(reference, first_lead, last_lead, bbox=BBOX, workers=3):
    """Return control-run interval fields on a native-grid subset.

    Leads are interval *boundaries*, so 10..34 gives 24 hourly intervals.
    Surface state is averaged from the two endpoints. No temporal gap filling.
    """
    validate_bbox(bbox)
    ref = utc(reference)
    if first_lead < 1 or last_lead <= first_lead:
        raise ValueError("Use positive, increasing boundary leads, e.g. 10..34")
    ref_string = ref.strftime("%Y-%m-%dT%H:%M:%SZ")
    assets = _request(f"{STAC}/collections/{COLLECTION}/assets").json()["assets"]
    asset = next(a for a in assets if a["id"].startswith("horizontal"))
    raw = _request(asset["href"]).content
    decoded = _decode_bytes(raw)
    fields = {m["shortName"].lower(): (m, v) for m, v, _ in decoded}
    if fields["h"][0]["units"] != "m":
        raise ValueError("ICON surface height must be metres")
    lat, lon = fields["tlat"][1], fields["tlon"][1]
    for k in ("tlat", "tlon"):
        if fields[k][0]["units"] not in ("degree", "degrees", "degrees_north", "degrees_east", "Degree N", "Degree E"):
            raise ValueError(f"Unexpected ICON coordinate units: {fields[k][0]['units']}")
    w, s, e, n = bbox
    mask = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    ids = np.flatnonzero(mask)
    if len(ids) == 0:
        raise ValueError("No model cells inside bbox")
    grid = fields["tlat"][0]["uuidOfHGrid"]
    manifest = [{"source": f"{STAC}/collections/{COLLECTION}/assets",
                 "asset": asset["id"], "sha256": hashlib.sha256(raw).hexdigest()}]
    leads = list(range(first_lead, last_lead+1))
    variables = ("ASOD_S", "PS", "ALB_RAD", "SNOWC")

    def fetch(job):
        var, lead = job
        body = {"collections": [COLLECTION], "forecast:reference_datetime": ref_string,
                "forecast:variable": var, "forecast:perturbed": False,
                "forecast:horizon": f"P{lead//24}DT{lead%24:02d}H00M00S"}
        features = _request(STAC+"/search", body).json()["features"]
        if len(features) != 1:
            raise RuntimeError(f"Expected one ICON asset for {var} lead {lead}; found {len(features)} (expired/incomplete run?)")
        feature = features[0]
        name, entry = next(iter(feature["assets"].items()))
        content = _request(entry["href"]).content
        messages = _decode_bytes(content)
        if len(messages) != 1:
            raise ValueError("Expected one ICON control message")
        m, v, _ = messages[0]
        if (m.get("uuidOfHGrid") != grid or m["dataDate"] != int(ref.strftime("%Y%m%d"))
            or m["dataTime"] != int(ref.strftime("%H%M")) or m["endStep"] != lead
            or m["stepUnits"] != 1 or len(v) != len(lat)):
            raise ValueError(f"ICON reference/grid/time mismatch for {var}")
        expected_units = {"ASOD_S": "W m**-2", "PS": "Pa", "ALB_RAD": "%", "SNOWC": "%"}
        if m["units"] != expected_units[var]:
            raise ValueError(f"Unexpected units for {var}: {m['units']}")
        if var == "ASOD_S" and (m["stepType"] != "avg" or m["startStep"] != 0):
            raise ValueError("ICON ASOD_S must be mean since reference time")
        if var != "ASOD_S" and m["stepType"] != "instant":
            raise ValueError(f"Expected instantaneous {var}")
        if not np.all(np.isfinite(v[ids])):
            raise ValueError(f"Missing ICON cells in {var}")
        source = next(link["href"] for link in feature["links"] if link["rel"] == "self")
        return job, v[ids], m, {"source": source, "asset": name,
                               "sha256": hashlib.sha256(content).hexdigest()}

    records = {}
    jobs = [(v, h) for v in variables for h in leads]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (job, values, meta, source) in enumerate(pool.map(fetch, jobs), 1):
            records[job] = (values, meta)
            manifest.append(source)
            if i % 10 == 0 or i == len(jobs):
                print(f"ICON assets {i}/{len(jobs)}, subset {len(ids)} cells", flush=True)
    sw = interval_radiation(leads, [records["ASOD_S", h][0] for h in leads],
                            [records["ASOD_S", h][1]["packingError"] for h in leads])
    state = {}
    for var, out, divisor in (("PS", "pressure_pa", 1), ("ALB_RAD", "sw_albedo", 100),
                              ("SNOWC", "snow_fraction", 100)):
        v = np.array([records[var, h][0] for h in leads])/divisor
        state[out] = (("time", "cell"), (v[:-1]+v[1:])/2)
    base = np.datetime64(ref.replace(tzinfo=None), "ns")
    boundaries = base + np.asarray(leads)*np.timedelta64(1, "h")
    ds = xr.Dataset(dict(state, sw_down=(("time", "cell"), sw),
                         time_bounds=(("time", "bounds"), np.column_stack([boundaries[:-1], boundaries[1:]]))),
                    coords={"time": boundaries[:-1]+np.timedelta64(30, "m"), "cell": ids,
                            "latitude": ("cell", lat[ids]), "longitude": ("cell", lon[ids]),
                            "altitude_m": ("cell", fields["h"][1][ids])},
                    attrs={"forecast_reference_time": ref_string, "grid_uuid": grid,
                           "member": 0, "bbox": json.dumps(list(bbox)),
                           "icon_sources": json.dumps(manifest),
                           "source": "MeteoSwiss ICON-CH2 control, public STAC",
                           "surface_time_treatment": "mean of interval endpoint states"})
    for name, units in {"sw_down": "W m-2", "pressure_pa": "Pa", "sw_albedo": "1",
                        "snow_fraction": "1", "latitude": "degrees_north",
                        "longitude": "degrees_east", "altitude_m": "m"}.items():
        ds[name].attrs["units"] = units
    ds.time.attrs["bounds"] = "time_bounds"
    ds.sw_down.attrs["cell_methods"] = "time: mean"
    return ds


def cams_request(reference, hours, bbox=BBOX):
    ref = utc(reference)
    if ref.hour not in (0, 12) or ref.minute or ref.second:
        raise ValueError("CAMS reference must be 00 or 12 UTC")
    validate_bbox(bbox)
    hours = list(hours)
    if (len(hours) < 2 or any(not isinstance(h, (int, np.integer)) or h < 0 or h > 120 for h in hours)
        or not np.all(np.diff(hours) > 0)):
        raise ValueError("CAMS needs at least two increasing forecast hours within 0..120")
    w, s, e, n = bbox
    return {"date": ref.strftime("%Y-%m-%d"), "time": ref.strftime("%H:%M"),
            "type": "forecast", "leadtime_hour": [str(h) for h in hours],
            "variable": ["total_column_ozone", "total_aerosol_optical_depth_550nm"],
            "area": [float(np.ceil(n+1)), float(np.floor(w-1)),
                     float(np.floor(s-1)), float(np.ceil(e+1))], "data_format": "grib"}


def fetch_cams(reference, hours, output, bbox=BBOX):
    """Official open dataset; requires the user's ADS account/licence acceptance."""
    import cdsapi
    request = cams_request(reference, hours, bbox)
    client = cdsapi.Client(url="https://ads.atmosphere.copernicus.eu/api", retry_max=3, sleep_max=20, timeout=60)
    client.retrieve(CAMS_DATASET, request, str(output))
    Path(str(output)+".json").write_text(json.dumps(
        {"dataset": CAMS_DATASET, "reference": utc(reference).isoformat(), "request": request,
         "sha256": hashlib.sha256(Path(output).read_bytes()).hexdigest()}, indent=2)+"\n")


def load_cams(path):
    """Read a single CAMS forecast cycle: GRIB or normalized NetCDF.

    NetCDF contract: ozone_du and aod550(time,latitude,longitude), units DU and 1,
    forecast_reference_time attribute. No surface ozone substitutions.
    """
    path = Path(path)
    with path.open("rb") as f:
        is_grib = f.read(4) == b"GRIB"
    if not is_grib:
        with xr.open_dataset(path) as source:
            ds = source.load()
    else:
        arrays = {"ozone_du": {}, "aod550": {}}
        refs = set()
        target_lat = target_lon = None
        for m, values, coords in grib_messages(path):
            if m["shortName"] not in ("gtco3", "tco3", "aod550"):
                continue
            if coords is None:
                raise ValueError("CAMS input must be on ADS regular latitude/longitude grid")
            refs.add((m["dataDate"], m["dataTime"]))
            lat, lon = coords
            lon = (lon+180) % 360 - 180
            ys, xs = np.unique(lat), np.unique(lon)
            if len(ys)*len(xs) != len(values):
                raise ValueError("Incomplete/duplicate CAMS spatial grid")
            if target_lat is not None and (not np.array_equal(ys, target_lat) or not np.array_equal(xs, target_lon)):
                raise ValueError("CAMS messages use different grids")
            target_lat, target_lon = ys, xs
            v = np.empty((len(ys), len(xs)))
            v[np.searchsorted(ys, lat), np.searchsorted(xs, lon)] = values
            key = "aod550" if m["shortName"] == "aod550" else "ozone_du"
            if key == "ozone_du":
                if m["units"] not in ("kg m**-2", "kg m-2"):
                    raise ValueError("Expected CAMS ozone kg/m²")
                v /= DU_KG_M2
            elif m["units"] not in ("~", "1", "Numeric", "dimensionless"):
                raise ValueError("Expected dimensionless CAMS AOD")
            if m["stepType"] != "instant":
                raise ValueError("Expected instantaneous CAMS composition")
            valid = datetime.strptime(f"{m['validityDate']}{m['validityTime']:04d}", "%Y%m%d%H%M")
            if valid in arrays[key]:
                raise ValueError("Duplicate CAMS valid time")
            arrays[key][valid] = v
        if len(refs) != 1 or not arrays["ozone_du"] or set(arrays["ozone_du"]) != set(arrays["aod550"]):
            raise ValueError("Need matching ozone/AOD times from exactly one CAMS cycle")
        times = sorted(arrays["ozone_du"])
        date, hour = refs.pop()
        ref = datetime.strptime(f"{date}{hour:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        ds = xr.Dataset({k: (("time", "latitude", "longitude"), np.array([a[t] for t in times]))
                         for k, a in arrays.items()},
                        coords={"time": np.array(times, dtype="datetime64[ns]"),
                                "latitude": target_lat, "longitude": target_lon},
                        attrs={"forecast_reference_time": ref.isoformat(), "source": CAMS_DATASET})
        ds.ozone_du.attrs["units"] = "DU"
        ds.aod550.attrs["units"] = "1"
    for name, units in (("ozone_du", "DU"), ("aod550", "1")):
        if name not in ds or ds[name].attrs.get("units") != units:
            raise ValueError(f"CAMS contract requires {name} in {units}")
        if ds[name].dims != ("time", "latitude", "longitude"):
            raise ValueError("CAMS dimensions must be time,latitude,longitude")
        if not np.all(np.isfinite(ds[name])):
            raise ValueError(f"Missing CAMS {name}")
    utc(ds.attrs["forecast_reference_time"])
    for dim in ("time", "latitude", "longitude"):
        ds = ds.sortby(dim)
        a = ds[dim].values
        if len(a) < 2 or len(np.unique(a)) != len(a):
            raise ValueError(f"CAMS {dim} needs at least two unique coordinates")
    if np.any((ds.ozone_du < 100) | (ds.ozone_du > 700)) or np.any((ds.aod550 < 0) | (ds.aod550 > 10)):
        raise ValueError("Implausible CAMS ozone/AOD; check units")
    ds.attrs["input_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return ds


def write_netcdf(ds, path):
    """Atomic publication; data flags remain integer, times have explicit UTC units."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = {name: {"zlib": True, "complevel": 2, "dtype": "float32"}
                for name, v in ds.data_vars.items() if v.dtype.kind == "f"}
    for name in ("time", "time_bounds"):
        if name in ds:
            encoding[name] = {"units": "seconds since 1970-01-01 00:00:00", "calendar": "proleptic_gregorian"}
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".nc", delete=False) as f:
        tmp = Path(f.name)
    try:
        ds.to_netcdf(tmp, engine="netcdf4", encoding=encoding)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
