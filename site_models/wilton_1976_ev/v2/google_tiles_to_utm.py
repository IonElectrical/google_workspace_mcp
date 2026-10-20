"""Move a Blosm Google Photorealistic 3D Tiles import into the UTM 19N / NAVD88 frame of
Wilton1976_Downtown_v2.blend, then snap it vertically onto the lidar terrain.

Google tiles are VISUAL CONTEXT ONLY: never measure from them (precedence: lidar / site
measurement > parcels > orthophoto > OSM > Google).

1. Blosm panel (N > Blosm): the extent and "3D Tiles / Google" are pre-set; click import.
2. Scripting tab > this text > Run Script.

Exact per-vertex conversion: Blosm local -> ECEF (Blosm's own float32 origin and rotation) ->
geodetic -> UTM 19N; heights are WGS84-ellipsoidal, so the mesh is then lifted by an approximate
geoid separation and fine-aligned to the lidar ground (mode of ground differences).
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

ALIGN_VERTICAL = True
APPROX_GEOID_N = -28.4  # m, southern NH; the fine alignment removes the residual
E0, N0 = 276000.0, 4747000.0
_A, _B = 6378137.0, 6356752.3142451793
_E2 = 1.0 - (_B * _B) / (_A * _A)
_F_UTM, _A_UTM = 1 / 298.257222101, 6378137.0


def blosm_center_f32(lat, lon):
    try:
        from threed_tiles.manager import BaseManager

        return Vector(BaseManager.fromGeographic(lat, lon, 0.0))
    except ImportError:
        rs = (6378137.0**2, 6378137.0**2, 6356752.3142451793**2)
        la, lo = math.radians(lat), math.radians(lon)
        n = Vector(
            (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
        )
        n.normalize()
        k = Vector((rs[0] * n[0], rs[1] * n[1], rs[2] * n[2]))
        k /= math.sqrt(n.dot(k))
        return k


def ecef_to_geodetic(p):
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    lon = np.arctan2(y, x)
    r = np.hypot(x, y)
    ep2 = (_A * _A - _B * _B) / (_B * _B)
    th = np.arctan2(z * _A, r * _B)
    lat = np.arctan2(z + ep2 * _B * np.sin(th) ** 3, r - _E2 * _A * np.cos(th) ** 3)
    n = _A / np.sqrt(1 - _E2 * np.sin(lat) ** 2)
    return np.degrees(lat), np.degrees(lon), r / np.cos(lat) - n


def utm19(lat, lon):
    n = _F_UTM / (2 - _F_UTM)
    a = _A_UTM / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    al = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    ]
    e = math.sqrt(_F_UTM * (2 - _F_UTM))
    phi, lam = np.radians(lat), np.radians(lon + 69.0)
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xp, ep = np.arctan2(t, np.cos(lam)), np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    xi, eta = xp.copy(), ep.copy()
    for j, c in enumerate(al, 1):
        xi = xi + c * np.sin(2 * j * xp) * np.cosh(2 * j * ep)
        eta = eta + c * np.cos(2 * j * xp) * np.sinh(2 * j * ep)
    return 500000.0 + 0.9996 * a * eta, 0.9996 * a * xi


def vertical_shift(google, terrain):
    from mathutils.bvhtree import BVHTree

    dg = bpy.context.evaluated_depsgraph_get()
    tt = BVHTree.FromObject(terrain, dg)
    gts = [(o, BVHTree.FromObject(o, dg)) for o in google]
    diffs = []
    for i in range(-30, 31):
        for j in range(-30, 31):
            x, y = 180 + i * 4.0, 120 + j * 4.0
            lt, *_ = tt.ray_cast(Vector((x, y, 3000)), Vector((0, 0, -1)))
            if lt is None:
                continue
            zs = []
            for o, t in gts:
                lg, *_ = t.ray_cast(
                    o.matrix_world.inverted() @ Vector((x, y, 3000)), Vector((0, 0, -1))
                )
                if lg is not None:
                    zs.append((o.matrix_world @ lg).z)
            if zs:
                diffs.append(max(zs) - lt.z)
    if len(diffs) < 50:
        return None, len(diffs)
    bins = {}
    for d in diffs:
        if -20 < d < 20:
            bins.setdefault(round(d / 0.2), []).append(d)
    peak = sorted(max(bins.values(), key=len))
    c = peak[len(peak) // 2]
    near = sorted(d for d in diffs if abs(d - c) < 0.5)
    return near[len(near) // 2], len(near)


def main():
    scene = bpy.context.scene
    lat0, lon0 = float(scene["lat"]), float(scene["lon"])
    c32 = blosm_center_f32(lat0, lon0)
    psi = math.atan(c32[2] / math.sqrt(c32[0] ** 2 + c32[1] ** 2))
    q = Matrix.Rotation(psi - math.pi / 2, 3, "X") @ Matrix.Rotation(
        math.radians(-90.0 - lon0), 3, "Z"
    )
    qn = np.array(q, dtype=np.float64)
    cn = np.array(c32[:], dtype=np.float64)
    google = [
        o
        for c in bpy.data.collections
        if c.name.startswith(("Google 3D Tiles", "3D Tiles"))
        for o in c.all_objects
        if o.type == "MESH"
    ]
    if not google:
        raise RuntimeError("No imported 3D Tiles found - run the Blosm import first")
    for o in google:
        me = o.data
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(o.matrix_world, dtype=np.float64)
        world = co @ mw[:3, :3].T + mw[:3, 3]
        ecef = world @ qn + cn  # inverse of P = Q (ECEF - C32)
        lat, lon, h = ecef_to_geodetic(ecef)
        e, n = utm19(lat, lon)
        out = np.column_stack(
            [
                np.asarray(e) - E0,
                np.asarray(n) - N0,
                h - (APPROX_GEOID_N if ALIGN_VERTICAL else 0.0),
            ]
        )
        o.matrix_world = Matrix.Identity(4)
        me.vertices.foreach_set("co", out.astype(np.float32).ravel())
        me.update()
        o["frame"] = (
            "UTM 19N local (E-276000, N-4747000), z ~ NAVD88 after alignment - VISUAL ONLY"
        )
    msg = "moved to UTM 19N"
    if ALIGN_VERTICAL:
        terrain = next(o for o in scene.objects if o.name.startswith("Terrain detail"))
        shift, n = vertical_shift(google, terrain)
        if shift is not None:
            for o in google:
                o.location.z -= shift
            msg += f"; vertical fine-align {-shift:+.2f} m from {n} ground samples"
        else:
            msg += "; vertical fine-align skipped (too few overlapping samples)"
    scene["google_tiles_frame"] = msg
    print("google_tiles_to_utm:", msg)


main()
