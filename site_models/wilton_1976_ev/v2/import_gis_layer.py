"""Import a GIS layer (Shapefile .shp or GeoJSON) into Wilton1976_Downtown_v2.blend, draped on the
lidar terrain, in the scene's UTM 19N frame. Use it for FEMA NFHL (S_FLD_HAZ_AR / S_BFE), NWI
wetlands, GRANIT / Town parcels, or anything digitised in QGIS.

Blender: Scripting tab -> open this text -> edit the two lines under SETTINGS -> Run Script.

CRS is read from the .prj (or GeoJSON = lon/lat): geographic NAD83/WGS84, NH State Plane
(EPSG:3437 / 3445, US feet), NH State Plane metres (EPSG:26986... not NH - rejected), or UTM 19N
(EPSG:26919 / 6348). Anything else stops with a message - reproject in QGIS first.
Pure Python + numpy; no add-ons needed.
"""

import json
import math
import os
import struct

import bpy
import numpy as np

# ------------------------------------------------------------------ SETTINGS
PATH = "/Users/YOU/Downloads/NFHL_33011C/S_FLD_HAZ_AR.shp"  # .shp or .geojson
LAYER_NAME = "FEMA flood hazard areas"  # becomes the collection name
LABEL_FIELDS = [
    "FLD_ZONE",
    "ZONE_SUBTY",
    "STATIC_BFE",
    "ELEV",
    "MAP_LOT",
    "OWNER",
    "ATTRIBUTE",
    "WETLAND_TY",
]  # shown if present
# ---------------------------------------------------------------------------

E0, N0 = 276000.0, 4747000.0
_A, _F = 6378137.0, 1 / 298.257222101
US_FT = 1200.0 / 3937.0


def _coeffs(f):
    n = f / (2 - f)
    a = _A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    al = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    ]
    be = [n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96, n**2 / 48 + n**3 / 15, 17 * n**3 / 480]
    de = [2 * n - 2 * n**2 / 3 - 2 * n**3, 7 * n**2 / 3 - 8 * n**3 / 5, 56 * n**3 / 15]
    return a, al, be, de


def tm_fwd(lat, lon, lon0, k0, fe, fn=0.0, lat0=0.0):
    a, al, _, _ = _coeffs(_F)
    e = math.sqrt(_F * (2 - _F))
    phi, lam = np.radians(lat), np.radians(np.asarray(lon) - lon0)
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xp, ep = np.arctan2(t, np.cos(lam)), np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    xi, eta = xp.copy(), ep.copy()
    for j, c in enumerate(al, 1):
        xi = xi + c * np.sin(2 * j * xp) * np.cosh(2 * j * ep)
        eta = eta + c * np.cos(2 * j * xp) * np.sinh(2 * j * ep)
    m0 = tm_fwd(lat0, lon0, lon0, k0, 0.0)[1] if lat0 else 0.0
    return fe + k0 * a * eta, fn + k0 * a * xi - m0


def tm_inv(x, y, lon0, k0, fe, fn=0.0, lat0=0.0):
    a, _, be, de = _coeffs(_F)
    m0 = tm_fwd(lat0, lon0, lon0, k0, 0.0)[1] if lat0 else 0.0
    xi, eta = (np.asarray(y) - fn + m0) / (k0 * a), (np.asarray(x) - fe) / (k0 * a)
    xp, ep = xi.copy(), eta.copy()
    for j, c in enumerate(be, 1):
        xp = xp - c * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        ep = ep - c * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    chi = np.arcsin(np.sin(xp) / np.cosh(ep))
    phi = chi.copy()
    for j, c in enumerate(de, 1):
        phi = phi + c * np.sin(2 * j * chi)
    return np.degrees(phi), lon0 + np.degrees(np.arctan2(np.sinh(ep), np.cos(xp)))


def to_scene_fn(prj):
    p = (prj or "").upper()
    if not p or p.startswith("GEOGCS") or "GEOGCRS" in p[:10]:
        return lambda x, y: (
            np.asarray(tm_fwd(y, x, -69.0, 0.9996, 500000.0)[0]) - E0,
            np.asarray(tm_fwd(y, x, -69.0, 0.9996, 500000.0)[1]) - N0,
        ), "geographic lon/lat"
    if "UTM" in p and ("19N" in p or "ZONE_19N" in p or "ZONE 19N" in p):
        return lambda x, y: (np.asarray(x) - E0, np.asarray(y) - N0), "UTM 19N metres"
    if "NEW_HAMPSHIRE" in p or "NEW HAMPSHIRE" in p:
        feet = "FOOT" in p or "FEET" in p
        unit = US_FT if feet else 1.0

        def f(x, y):
            lat, lon = tm_inv(
                np.asarray(x) * unit,
                np.asarray(y) * unit,
                -71.66666666666667,
                0.999966667,
                300000.0,
                0.0,
                42.5,
            )
            e, n = tm_fwd(lat, lon, -69.0, 0.9996, 500000.0)
            return np.asarray(e) - E0, np.asarray(n) - N0

        return f, "NH State Plane " + ("US feet" if feet else "metres")
    raise RuntimeError(
        "Unsupported CRS in .prj - reproject to EPSG:26919 or EPSG:4269 in QGIS first:\n"
        + prj[:200]
    )


def read_dbf(path):
    with open(path, "rb") as fh:
        head = fh.read(32)
        nrec, hlen, rlen = struct.unpack("<IHH", head[4:12])
        fields = []
        while True:
            d = fh.read(32)
            if d[0] == 0x0D:
                break
            fields.append((d[:11].split(b"\0")[0].decode("latin1"), chr(d[11]), d[16]))
        fh.seek(hlen)
        rows = []
        for _ in range(nrec):
            rec = fh.read(rlen)
            pos, row = 1, {}
            for name, typ, ln in fields:
                raw = rec[pos : pos + ln].decode("latin1").strip()
                pos += ln
                if typ in "NF" and raw:
                    try:
                        raw = float(raw)
                    except ValueError:
                        pass
                row[name] = raw
            rows.append(row)
    return rows


def read_shp(path):
    """-> list of (kind, parts) with kind in point/line/polygon and parts = list of (n,2) arrays."""
    out = []
    with open(path, "rb") as fh:
        fh.seek(100)
        while True:
            h = fh.read(8)
            if len(h) < 8:
                break
            _, clen = struct.unpack(">ii", h)
            body = fh.read(clen * 2)
            st = struct.unpack("<i", body[:4])[0]
            if st == 0:
                out.append((None, []))
            elif st in (1, 11, 21):
                out.append(("point", [np.array([struct.unpack("<2d", body[4:20])])]))
            elif st in (3, 5, 13, 15, 23, 25):
                nparts, npts = struct.unpack("<2i", body[36:44])
                parts = struct.unpack(f"<{nparts}i", body[44 : 44 + 4 * nparts])
                xy = np.frombuffer(
                    body[44 + 4 * nparts : 44 + 4 * nparts + 16 * npts], dtype="<f8"
                ).reshape(-1, 2)
                bounds = list(parts) + [npts]
                out.append(
                    (
                        "line" if st in (3, 13, 23) else "polygon",
                        [xy[bounds[i] : bounds[i + 1]] for i in range(nparts)],
                    )
                )
            else:
                out.append((None, []))
    return out


def read_geojson(path):
    data = json.load(open(path))
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    geoms, rows = [], []
    for f in feats:
        g = f["geometry"]
        t, c = g["type"], g["coordinates"]
        if t == "Point":
            geoms.append(("point", [np.array([c[:2]])]))
        elif t == "LineString":
            geoms.append(("line", [np.array(c)[:, :2]]))
        elif t == "MultiLineString":
            geoms.append(("line", [np.array(p)[:, :2] for p in c]))
        elif t == "Polygon":
            geoms.append(("polygon", [np.array(r)[:, :2] for r in c]))
        elif t == "MultiPolygon":
            geoms.append(("polygon", [np.array(r)[:, :2] for p in c for r in p]))
        else:
            geoms.append((None, []))
        rows.append(f.get("properties") or {})
    return geoms, rows


def main():
    scene = bpy.context.scene
    terrain = next(
        (o for o in scene.objects if o.name.startswith("Terrain detail")), None
    )
    overview = next(
        (o for o in scene.objects if o.name.startswith("Terrain overview")), None
    )
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    dg = bpy.context.evaluated_depsgraph_get()
    trees = [(o, BVHTree.FromObject(o, dg)) for o in (terrain, overview) if o]

    def ground(x, y):
        for o, t in trees:
            loc, *_ = t.ray_cast(
                o.matrix_world.inverted() @ Vector((x, y, 3000.0)), Vector((0, 0, -1))
            )
            if loc is not None:
                return (o.matrix_world @ loc).z
        return 100.0

    if PATH.lower().endswith((".geojson", ".json")):
        geoms, rows = read_geojson(PATH)
        fn, crs = to_scene_fn("")
    else:
        prj_path = os.path.splitext(PATH)[0] + ".prj"
        fn, crs = to_scene_fn(open(prj_path).read() if os.path.exists(prj_path) else "")
        geoms, rows = read_shp(PATH), read_dbf(os.path.splitext(PATH)[0] + ".dbf")
    col = bpy.data.collections.new(f"{LAYER_NAME} (imported, {crs})")
    scene.collection.children.link(col)
    palette = [
        (0.1, 0.4, 1.0, 0.45),
        (1.0, 0.3, 0.1, 0.45),
        (0.2, 0.8, 0.3, 0.45),
        (0.9, 0.8, 0.1, 0.45),
        (0.7, 0.3, 0.9, 0.45),
    ]
    mats, n_in = {}, 0
    for i, ((kind, parts), row) in enumerate(zip(geoms, rows)):
        if not kind:
            continue
        sp = [np.column_stack(fn(p[:, 0], p[:, 1])) for p in parts]
        if all((abs(p[:, 0]) > 6000).all() or (abs(p[:, 1]) > 6000).all() for p in sp):
            continue  # outside the model
        n_in += 1
        key = str(row.get(LABEL_FIELDS[0]) or row.get(next(iter(row), ""), "") or kind)
        if key not in mats:
            m = bpy.data.materials.new(f"{LAYER_NAME}: {key}")
            m.diffuse_color = palette[len(mats) % len(palette)]
            mats[key] = m
        text = " | ".join(
            f"{k}={row[k]}"
            for k in LABEL_FIELDS
            if k in row and row[k] not in ("", None)
        )
        name = f"{LAYER_NAME} {i} {text}"[:60]
        if kind == "polygon":
            import bmesh

            bm = bmesh.new()
            for ring in sp:
                if len(ring) < 3:
                    continue
                vs = [bm.verts.new((x, y, ground(x, y) + 0.08)) for x, y in ring[:-1]]
                if len(vs) >= 3:
                    try:
                        bm.faces.new(vs)
                    except ValueError:
                        pass
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            me = bpy.data.meshes.new(name)
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(name, me)
            ob.data.materials.append(mats[key])
        else:
            cu = bpy.data.curves.new(name, "CURVE")
            cu.dimensions, cu.bevel_depth = "3D", 0.25 if kind == "line" else 0.0
            for ring in sp:
                s = cu.splines.new("POLY")
                s.points.add(len(ring) - 1)
                for p, (x, y) in zip(s.points, ring):
                    p.co = (x, y, ground(x, y) + 0.3, 1)
            ob = bpy.data.objects.new(name, cu)
            ob.data.materials.append(mats[key])
        for k, v in row.items():
            if isinstance(v, (int, float, str)) and len(str(k)) < 60:
                ob[k] = v
        ob["source_file"] = os.path.basename(PATH)
        col.objects.link(ob)
    print(
        f"import_gis_layer: {n_in} features inside the model from {os.path.basename(PATH)} ({crs})"
    )


main()
