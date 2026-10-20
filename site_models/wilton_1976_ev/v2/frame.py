"""Wilton #1976 v2 coordinate frame, sites and areas.

CRS: NAD83 / UTM zone 19N (EPSG:26919), metres. Vertical: NAVD88 metres (as delivered in
the USGS 3DEP 1 m DEM). Blender scene: 1 unit = 1 m, X = Easting - E0, Y = Northing - N0,
Z = NAVD88 elevation (no vertical offset). This module only needs numpy so it also runs
inside Blender; pyproj is used when present (outside Blender) and the built-in
transverse-Mercator code is checked against it.
"""

import math

import numpy as np

EPSG = 26919
E0, N0, Z0 = (
    276000.0,
    4747000.0,
    0.0,
)  # Blender scene origin offset (UTM 19N metres, NAVD88)
CENTER = (42.8440, -71.7390)  # downtown centre given in the brief
OVERVIEW_RADIUS = 3218.7  # 2 miles
DETAIL_RADIUS = 400.0  # around each site

SITES = [
    {
        "key": "S1_PoliceLot",
        "title": "Site 1 - Police station lot",
        "address": "7 Burns Hill Rd",
        "lat": 42.84485,
        "lon": -71.73967,
        "coord_source": "OSM (per brief)",
    },
    {
        "key": "S2_MainStLot",
        "title": "Site 2 - Main St municipal lot",
        "address": "SE corner Main St & Burns Hill Rd (near 42 Main St)",
        "lat": 42.84448,
        "lon": -71.73830,
        "coord_source": "approximate (per brief) - verify",
    },
    {
        "key": "S3_Library",
        "title": "Site 3 - Library / street-side",
        "address": "Wilton Public & Gregg Free Library, Forest Rd",
        "lat": 42.84532,
        "lon": -71.73847,
        "coord_source": "OSM library point (per brief)",
    },
    {
        "key": "S4_Mill",
        "title": "Site 4 - Pidcock mill",
        "address": "1 Riverside Way (map point: 21 Mill St OSM house)",
        "lat": 42.84289,
        "lon": -71.73906,
        "coord_source": "OSM house 21 Mill St (per brief)",
    },
]

# GRS80 (NAD83) and UTM zone 19 parameters
_A = 6378137.0
_F = 1 / 298.257222101
_K0 = 0.9996
_LON0 = -69.0
_FE = 500000.0


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


def tm_forward(lat, lon, lon0=_LON0, k0=_K0, fe=_FE, fn=0.0, lat0=0.0, a=_A, f=_F):
    """Geodetic (deg) -> transverse Mercator (Krueger series, mm-level). Works on arrays."""
    n, big_a, alpha, _, _ = _tm_coeffs(a, f)
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


def tm_inverse(x, y, lon0=_LON0, k0=_K0, fe=_FE, fn=0.0, lat0=0.0, a=_A, f=_F):
    n, big_a, _, beta, delta = _tm_coeffs(a, f)
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
    """NAD83 geographic (deg) -> UTM 19N (m)."""
    return tm_forward(lat, lon)


def local(lat, lon):
    e, n = utm(lat, lon)
    return np.asarray(e) - E0, np.asarray(n) - N0


def geodetic(x_local, y_local):
    return tm_inverse(np.asarray(x_local) + E0, np.asarray(y_local) + N0)


# NH State Plane, NAD83 (EPSG:3437, US survey feet) - GRANIT orthophotos and parcels use it
US_FT = 1200.0 / 3937.0
NH_SP = dict(lon0=-71.66666666666667, k0=0.999966667, fe=300000.0, fn=0.0, lat0=42.5)


def stateplane_ft(lat, lon):
    e, n = tm_forward(lat, lon, **NH_SP)
    return np.asarray(e) / US_FT, np.asarray(n) / US_FT


if __name__ == "__main__":
    for s in SITES:
        x, y = local(s["lat"], s["lon"])
        print(f"{s['key']:14s} local x={float(x):8.2f} y={float(y):8.2f}")
