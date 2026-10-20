"""Site list and coordinate frame for Ion Electrical job #1976 (Wilton NH, RANH Level 2 chargers).

Every layer we build is expressed in the same local frame that the Blosm add-on uses
when it imports Google Photorealistic 3D Tiles, so a later Blosm import lands on top
of our open-data layers without any manual alignment:

    P_blender = Q @ (ECEF(lat, lon, h_ellipsoid) - ECEF(lat0, lon0, 0))
    Q = Rx(psi0 - 90deg) @ Rz(-90deg - lon0),  psi0 = geocentric latitude of the origin

(see blosm/threed_tiles/blender.py, BlenderRenderer.finalize). X points east, Y north,
Z is height above the WGS84 ellipsoid at the origin (about 28.6 m below NAVD88 here).
This module only needs numpy so it also runs inside Blender's bundled Python.
"""

import math

import numpy as np

JOB = "Wilton1976"
RADIUS_M = 200.0  # half-width of the square imported around each site

SITES = [
    {
        "key": "Site1_PoliceLot",
        "title": "Site 1 - Police station lot",
        "address": "7 Burns Hill Rd, Wilton NH 03086",
        "lat": 42.84485,
        "lon": -71.73967,
    },
    {
        "key": "Site2_MainSt",
        "title": "Site 2 - Main St curbside",
        "address": "Main St by Stony Brook and the Wilton Public & Gregg Free Library (7 Forest Rd)",
        "lat": 42.84532,
        "lon": -71.73847,
    },
    {
        "key": "Site3_MunicipalLot",
        "title": "Site 3 - Municipal lot",
        "address": "SE corner of Main St and Burns Hill Rd, near Town Hall (42 Main St) - approximate",
        "lat": 42.84448,
        "lon": -71.73830,
    },
]

# WGS84, same constants as blosm/threed_tiles/manager.py
_A = 6378137.0
_B = 6356752.3142451793
_E2 = 1.0 - (_B * _B) / (_A * _A)


def site_by_key(key):
    for site in SITES:
        if site["key"] == key:
            return site
    raise KeyError(key)


def blend_name(site):
    return f"{JOB}_{site['key']}"


def ecef(lat, lon, h):
    """Geodetic (degrees, metres above ellipsoid) to ECEF metres. Works on arrays."""
    lat = np.radians(np.asarray(lat, dtype=np.float64))
    lon = np.radians(np.asarray(lon, dtype=np.float64))
    h = np.asarray(h, dtype=np.float64)
    sin_lat = np.sin(lat)
    n = _A / np.sqrt(1.0 - _E2 * sin_lat * sin_lat)
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (n * (1.0 - _E2) + h) * sin_lat
    return np.stack([x, y, z], axis=-1)


class BlosmFrame:
    """Local frame identical to the one Blosm uses for Google 3D Tiles around (lat0, lon0)."""

    def __init__(self, lat0, lon0):
        self.lat0 = lat0
        self.lon0 = lon0
        self.origin = ecef(lat0, lon0, 0.0)
        cx, cy, cz = self.origin
        psi = math.atan(cz / math.sqrt(cx * cx + cy * cy))
        a = psi - math.pi / 2.0
        b = math.radians(-90.0 - lon0)
        rx = np.array(
            [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
        )
        rz = np.array(
            [[math.cos(b), -math.sin(b), 0], [math.sin(b), math.cos(b), 0], [0, 0, 1]]
        )
        self.q = rx @ rz
        self.q_inv = self.q.T

    def from_geodetic(self, lat, lon, h):
        """lat/lon degrees, h metres above the WGS84 ellipsoid -> (..., 3) local XYZ."""
        p = ecef(lat, lon, h) - self.origin
        return p @ self.q.T

    def to_geodetic(self, xyz):
        """Inverse of from_geodetic (Bowring's method, sub-millimetre at this scale)."""
        xyz = np.asarray(xyz, dtype=np.float64)
        p = xyz @ self.q_inv.T + self.origin
        x, y, z = p[..., 0], p[..., 1], p[..., 2]
        lon = np.arctan2(y, x)
        r = np.hypot(x, y)
        ep2 = (_A * _A - _B * _B) / (_B * _B)
        theta = np.arctan2(z * _A, r * _B)
        lat = np.arctan2(
            z + ep2 * _B * np.sin(theta) ** 3, r - _E2 * _A * np.cos(theta) ** 3
        )
        sin_lat = np.sin(lat)
        n = _A / np.sqrt(1.0 - _E2 * sin_lat * sin_lat)
        h = r / np.cos(lat) - n
        return np.degrees(lat), np.degrees(lon), h


def extent(site, radius_m=RADIUS_M):
    """(min_lon, min_lat, max_lon, max_lat) of the square around a site, as Blosm expects."""
    dlat = radius_m / 111132.954
    dlon = radius_m / (111319.488 * math.cos(math.radians(site["lat"])))
    return (
        round(site["lon"] - dlon, 6),
        round(site["lat"] - dlat, 6),
        round(site["lon"] + dlon, 6),
        round(site["lat"] + dlat, 6),
    )


def blosm_paste_string(site, radius_m=RADIUS_M):
    """String for Blosm's 'paste' extent button: min_lon,min_lat,max_lon,max_lat."""
    return ",".join(f"{v:.6f}" for v in extent(site, radius_m))


def union_extent(margin_m=60.0):
    boxes = [extent(s, RADIUS_M + margin_m) for s in SITES]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        # any spot: python sites.py LAT LON [RADIUS_M]  -> string for Blosm's "paste" button
        point = {"lat": float(sys.argv[1].rstrip(",")), "lon": float(sys.argv[2])}
        print(
            blosm_paste_string(
                point, float(sys.argv[3]) if len(sys.argv) > 3 else RADIUS_M
            )
        )
    else:
        for s in SITES:
            print(f"{blend_name(s):32s} paste extent: {blosm_paste_string(s)}")
