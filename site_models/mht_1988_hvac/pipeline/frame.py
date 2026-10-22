"""Coordinate frame for a location model, driven by the job config (FRAME section).

CRS: NAD83 / UTM (zone from the config), metres. Vertical: NAVD88 metres. Blender scene:
1 unit = 1 m, X = Easting - E0, Y = Northing - N0, Z = NAVD88 elevation. Only numpy is needed,
so this also runs inside Blender. The transverse-Mercator code (Krueger series) is checked
against pyproj by `python frame.py`.

The config is found from, in order: load_config(path), the JOB_CONFIG environment variable,
or ../job_config.py next to this pipeline folder.
"""

import importlib.util
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_CFG = None


def load_config(path=None):
    global _CFG
    path = (
        path
        or os.environ.get("JOB_CONFIG")
        or os.path.join(HERE, "..", "job_config.py")
    )
    spec = importlib.util.spec_from_file_location("job_config", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CONFIG_PATH = os.path.abspath(path)
    mod.JOB_DIR = os.path.dirname(mod.CONFIG_PATH)
    _CFG = mod
    _apply(mod)
    return mod


def cfg():
    return _CFG or load_config()


# GRS80 (NAD83)
_A = 6378137.0
_F = 1 / 298.257222101
_K0 = 0.9996
_FE = 500000.0
EPSG = E0 = N0 = Z0 = LON0 = None
OVERVIEW_RADIUS = DETAIL_RADIUS = None
SP = None
US_FT = 1200.0 / 3937.0


def _apply(c):
    global EPSG, E0, N0, Z0, LON0, OVERVIEW_RADIUS, DETAIL_RADIUS, SP
    f = c.FRAME
    EPSG, E0, N0, Z0, LON0 = f["epsg"], f["E0"], f["N0"], f["Z0"], f["utm_lon0"]
    OVERVIEW_RADIUS, DETAIL_RADIUS = f["overview_radius_m"], f["detail_radius_m"]
    SP = {k: f["state_plane"][k] for k in ("lon0", "k0", "fe", "fn", "lat0")}


def _tm_coeffs(a, f):
    n = f / (2 - f)
    big_a = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    alpha = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    ]
    beta = [
        n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96,
        n**2 / 48 + n**3 / 15,
        17 * n**3 / 480,
    ]
    delta = [
        2 * n - 2 * n**2 / 3 - 2 * n**3,
        7 * n**2 / 3 - 8 * n**3 / 5,
        56 * n**3 / 15,
    ]
    return n, big_a, alpha, beta, delta


def tm_forward(lat, lon, lon0, k0=_K0, fe=_FE, fn=0.0, lat0=0.0, a=_A, f=_F):
    """Geodetic (deg) -> transverse Mercator (Krueger series, mm-level). Works on arrays."""
    _, big_a, alpha, _, _ = _tm_coeffs(a, f)
    phi = np.radians(np.asarray(lat, dtype=np.float64))
    lam = np.radians(np.asarray(lon, dtype=np.float64) - lon0)
    e = math.sqrt(f * (2 - f))
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xi_p = np.arctan2(t, np.cos(lam))
    eta_p = np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    xi, eta = xi_p.copy(), eta_p.copy()
    for j, al in enumerate(alpha, start=1):
        xi = xi + al * np.sin(2 * j * xi_p) * np.cosh(2 * j * eta_p)
        eta = eta + al * np.cos(2 * j * xi_p) * np.sinh(2 * j * eta_p)
    m0 = 0.0
    if lat0:
        m0 = tm_forward(lat0, lon0, lon0, k0, 0.0, 0.0, 0.0, a, f)[1]
    return fe + k0 * big_a * eta, fn + k0 * big_a * xi - m0


def tm_inverse(x, y, lon0, k0=_K0, fe=_FE, fn=0.0, lat0=0.0, a=_A, f=_F):
    _, big_a, _, beta, delta = _tm_coeffs(a, f)
    m0 = tm_forward(lat0, lon0, lon0, k0, 0.0, 0.0, 0.0, a, f)[1] if lat0 else 0.0
    xi = (np.asarray(y, dtype=np.float64) - fn + m0) / (k0 * big_a)
    eta = (np.asarray(x, dtype=np.float64) - fe) / (k0 * big_a)
    xi_p, eta_p = xi.copy(), eta.copy()
    for j, be in enumerate(beta, start=1):
        xi_p = xi_p - be * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        eta_p = eta_p - be * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    chi = np.arcsin(np.sin(xi_p) / np.cosh(eta_p))
    phi = chi.copy()
    for j, de in enumerate(delta, start=1):
        phi = phi + de * np.sin(2 * j * chi)
    lam = np.arctan2(np.sinh(eta_p), np.cos(xi_p))
    return np.degrees(phi), lon0 + np.degrees(lam)


def utm(lat, lon):
    cfg()
    return tm_forward(lat, lon, LON0)


def local(lat, lon):
    e, n = utm(lat, lon)
    return np.asarray(e) - E0, np.asarray(n) - N0


def geodetic(x_local, y_local):
    cfg()
    return tm_inverse(np.asarray(x_local) + E0, np.asarray(y_local) + N0, LON0)


def stateplane_ft(lat, lon):
    cfg()
    e, n = tm_forward(lat, lon, **SP)
    return np.asarray(e) / US_FT, np.asarray(n) / US_FT


if __name__ == "__main__":
    from pyproj import Transformer

    c = cfg()
    lat0, lon0 = geodetic(0.0, 0.0)
    t = Transformer.from_crs(4326, c.FRAME["epsg"], always_xy=True)
    ts = Transformer.from_crs(4326, c.FRAME["state_plane"]["epsg"], always_xy=True)
    worst = 0.0
    for dx in (-1500, 0, 1500):
        for dy in (-1500, 0, 1500):
            la, lo = geodetic(float(dx), float(dy))
            e, n = t.transform(float(lo), float(la))
            worst = max(worst, math.hypot(e - E0 - dx, n - N0 - dy))
            es, ns = stateplane_ft(la, lo)
            e2, n2 = ts.transform(float(lo), float(la))
            worst = max(worst, math.hypot(float(es) - e2, float(ns) - n2) * US_FT)
    print(f"origin lat/lon {float(lat0):.7f}, {float(lon0):.7f}")
    sx, sy = stateplane_ft(lat0, lon0)
    print(f"origin NH State Plane ft E {float(sx):,.2f} N {float(sy):,.2f}")
    print(f"max difference vs pyproj over +-1.5 km: {worst * 1000:.3f} mm")
